import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_OFFLINE"] = "1"


import os
import re
import json
import psycopg
from dotenv import load_dotenv

load_dotenv()  # 确保 DEEPSEEK_API_KEY / POSTGRES_PASSWORD 等从 .env 加载

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from agent.state import AgentState, FinancialMetrics
from core.tools import search_tool
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_milvus import Milvus

# 初始化本地向量模型和 Milvus 连接
MILVUS_URI = "http://localhost:19530"
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-zh-v1.5")
vectorstore = Milvus(
    embedding_function=embeddings,
    collection_name="compliance_rules",
    connection_args={"uri": MILVUS_URI},
)

# 初始化大模型
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    temperature=0.1,
)


def extract_data_node(state: AgentState):
    print("--> [节点1] 正在从财报中提取核心数据...")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个专业的财务分析师。请从以下财报文本中提取出核心指标。
        必须返回严格的JSON格式，格式如下：
        {{"company_name": "公司名称", "industry": "所属行业", "revenue_current": 数字, "revenue_previous": 数字, "net_profit": 数字}}
        ⚠️ 必须统一单位为“亿元”！绝对不能编造数据！"""),
        ("human", "{text}")
    ])
    chain = prompt | llm
    response_text = chain.invoke({"text": state["raw_text"]}).content
    response_text = response_text.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(response_text)
        extracted_data = FinancialMetrics(**parsed)
    except Exception as e:
        print(f"    [解析失败] 模型返回: {response_text}")
        raise e

    metrics = extracted_data.model_dump()
    if 0 < metrics.get("revenue_current", 0) < 1:
        metrics["revenue_current"] = round(metrics["revenue_current"] * 100000000, 2)
        metrics["revenue_previous"] = round(metrics.get("revenue_previous", 0) * 100000000, 2)
        metrics["net_profit"] = round(metrics.get("net_profit", 0) * 100000000, 2)

    # ===== 用 LLM 从财报开头识别报告期（兼容年度/季度/港美股各种写法）=====
    head = state["raw_text"][:1500]
    period_prompt = f"""你是一个财报分析专家。请从下面的财报文本开头，识别出这份财报的报告期。

要求返回严格 JSON（不要 markdown 代码块）：
{{"report_year": "年份数字，如 2026", "report_period": "报告期类型，如 第三季度/年度/半年度/第一季度/第二季度/第四季度"}}

财报文本开头：
{head}
"""
    try:
        period_raw = llm.invoke(period_prompt).content
        period_raw = period_raw.replace("```json", "").replace("```", "").strip()
        period_info = json.loads(period_raw)
        report_year = str(period_info.get("report_year", "")).strip()
        report_period = str(period_info.get("report_period", "")).strip()
    except Exception as e:
        print(f"    ⚠️ LLM 识别报告期失败: {e}，启用正则兜底")
        head3000 = state["raw_text"][:3000]
        q = re.search(r"(20\d{2})\s*年\s*第([一二三四1-4])季度", head3000)
        y = re.search(r"(20\d{2})\s*年\s*年度报告", head3000)
        if q:
            report_year = q.group(1)
            cn = {"一": "第一季度", "二": "第二季度", "三": "第三季度", "四": "第四季度",
                  "1": "第一季度", "2": "第二季度", "3": "第三季度", "4": "第四季度"}
            report_period = cn.get(q.group(2), "季度")
        elif y:
            report_year = y.group(1)
            report_period = "年度"
        else:
            report_year, report_period = "", ""

    print(f"    [报告期(LLM识别)]: {report_year}年{report_period or '未识别'}")

    return {"metrics": metrics, "report_year": report_year, "report_period": report_period}


def calculate_node(state: AgentState):
    print("--> [节点2] 正在计算同比增长率...")
    metrics = state["metrics"]
    current = metrics["revenue_current"]
    previous = metrics["revenue_previous"]
    growth = ((current - previous) / previous) * 100 if previous != 0 else 0.0
    print(f"    [计算结果] 营收增长率: {growth:.2f}%")
    return {"growth_rate": round(growth, 2)}


def search_competitor_node(state: AgentState):
    print("--> [节点3] 正在识别同行业竞品并联网搜索营收数据...")
    company = state["metrics"].get("company_name", "未知公司")
    industry = state["metrics"].get("industry", "同行业")

    # 1) 让 LLM 先根据具体行业列出真正的竞品名字（关键！）
    name_prompt = f"""
    你是一个行业分析师。{company} 属于「{industry}」行业。
    请列出 3 家该行业与它最直接竞争、真实存在的公司名字。
    只输出公司名，用中文逗号分隔，不要解释、不要编号。
    示例格式：腾讯控股，哔哩哔哩，完美世界
    """
    names_raw = llm.invoke(name_prompt).content.strip()
    # 兼容中英文逗号切分，最多取 3 家
    names = [n.strip() for n in names_raw.replace("，", ",").split(",") if n.strip()][:3]
    print(f"    [AI识别的同行业竞品]: {names}")

    # 拿到 PDF 报告期（年 + 季度），用于竞品数据的时间线对齐
    report_year = state.get("report_year", "")
    report_period = state.get("report_period", "")
    # 季度报告不加"年报"二字，避免搜索引擎误匹配年度数据
    search_label = f"{report_year}年{report_period}" if report_year else ""

    # 2) 针对每家竞品单独搜营收（优先带报告期，搜不到则降级重试）
    competitor_text = ""
    for name in names:
        # 优先：带报告期精确搜索，让竞品数据和本公司报告期对齐
        queries = []
        if search_label:
            queries.append(f"{name} {search_label} 营业收入")
        queries.append(f"{name} 营业收入 年报")  # 兜底：不带年份

        chunk = ""
        for query in queries:
            print(f"    [搜索词]: {query}")
            try:
                results = search_tool.invoke(query)
                # 防御性解析（Tavily 新版返回 dict，内含 results 列表）
                # 统一抽成"条目列表"，只取 content，丢弃 query/images 等垃圾字段
                if isinstance(results, dict):
                    items = results.get("results", [])
                elif isinstance(results, list):
                    items = results
                elif isinstance(results, str):
                    items = [results]
                else:
                    items = []

                for item in items:
                    if isinstance(item, dict):
                        content = item.get("content", item.get("snippet", ""))
                        if content:
                            chunk += content + "\n"
                    elif isinstance(item, str):
                        chunk += item + "\n"
                if not chunk.strip():
                    chunk = str(results) if not isinstance(results, dict) else ""

                # 搜到有效内容就跳出，不再降级
                if len(chunk.strip()) > 10:
                    if search_label and query == queries[0]:
                        print(f"    ✅ [{name}] 命中 {search_label} 同期数据")
                    else:
                        print(f"    ⚠️ [{name}] 未找到 {search_label or report_year} 数据，已用最新年报兜底")
                    break
            except Exception as e:
                print(f"    ⚠️ 搜索失败: {e}")
                continue

        if chunk.strip():
            competitor_text += f"【{name}】{chunk.strip()}\n\n"


    print(f"    [搜索完成] 抓取到约 {len(competitor_text)} 个字符的同行数据。")
    return {"competitor_info": competitor_text}


def retrieve_compliance_node(state: AgentState):
    print("--> [节点3.5] 正在智能生成Query并检索 Milvus 合规知识库 (RAG)...")
    company = state["metrics"].get("company_name", "未知公司")
    industry = state["metrics"].get("industry", "未知行业")
    growth = state["growth_rate"]

    # 1) AI 动态检索词：根据行业特征 + 财务表现自己决定搜什么法条
    query_prompt = f"""
    公司：{company}，行业：{industry}，营收增长率：{growth}%。
    请结合该公司的行业特征与财务表现，生成一个精准的合规检索关键词（不超过15字，只输出关键词本身，不要解释）。
    参考方向：业绩下滑/亏损→业绩预告、重大损失披露；互联网/科技→数据安全、反垄断、个人信息保护；
    白酒/食品→消费税、食品安全；财务异常→财务造假、信息披露真实性。
    """
    dynamic_query = llm.invoke(query_prompt).content.strip()
    print(f"    [AI动态检索词]: {dynamic_query}")

    # 2) 确定性行业/场景兜底词：防止 AI 词跑偏导致三家命中同一批通用条款
    seed_queries = []
    if growth < 0:
        seed_queries.append("业绩下滑 业绩预告 修正公告 重大损失披露")
    if any(k in industry for k in ["互联网", "科技", "软件", "游戏", "传媒", "通信", "网络"]):
        seed_queries.append("数据安全 个人信息保护 反垄断 市场支配地位")
    if any(k in industry for k in ["白酒", "酒", "食品", "饮料"]):
        seed_queries.append("消费税 食品安全 税务合规")
    seed_queries.append("财务造假 虚报利润 信息披露真实准确完整")

    # 3) 多词检索 + 去重，最多保留 4 条互不重复的法条
    all_docs, seen = [], set()
    for q in [dynamic_query] + seed_queries:
        for doc in vectorstore.similarity_search(q, k=2):
            key = doc.page_content[:60]
            if key not in seen:
                seen.add(key)
                all_docs.append(doc)
        if len(all_docs) >= 4:
            break
    all_docs = all_docs[:4]
    rules = "\n\n".join([d.page_content for d in all_docs])

    print(f"    [检索完成] 命中 {len(all_docs)} 条不同合规条款。")
    return {"compliance_rules": rules}


def summary_node(state: AgentState):
    print("--> [节点4] 正在综合自身数据与竞品数据，生成对比研报...")
    metrics = state["metrics"]
    company = metrics['company_name']
    report_year = state.get('report_year', '')
    report_period = state.get('report_period', '')
    period_label = f"{report_year}年{report_period}" if report_period else (f"{report_year}年" if report_year else "")

    # 报告期口径：以财报原文识别的报告期为准，禁止模型自行推断
    if period_label:
        year_rule = (
            f"★ 报告期口径（强制）：本次分析的财报为【{period_label}】。"
            f"描述本公司数据时只能使用「{period_label}」「本期」「上期」这类表述，"
            f"绝对禁止把报告期写成年报或写成其他数字（如{int(report_year)-1}年、{int(report_year)-2}年）。"
        )
    else:
        year_rule = "★ 报告期口径（强制）：无法确定报告期，描述本公司时只用「本期」「上期」，禁止编造任何具体年份数字。"

    prompt = f"""
    你是一个资深金融投资与合规顾问。请根据以下数据，撰写一段财报分析摘要（约200字）。

    【本公司名称】{company}
    【自身数据】
    公司：{company} ({metrics['industry']})
    营收：{metrics['revenue_current']} 亿元，同比增长：{state['growth_rate']}%

    【竞品数据】（注意：这是同行业其他公司的数据，年份可能与本公司报告期不完全一致）
    {state['competitor_info']}

    【合规法条参考 (RAG检索)】
    {state.get('compliance_rules', '无相关法条')}

    ★★★ 输出规则（必须严格遵守，违反视为错误）★★★
    1. 【开头强制】摘要第一句必须以公司全称开头，格式为「{company}本期营收…」或「{company}202X年营收…」。禁止省略公司名，禁止只写「本期营收」「财报分析摘要」这类没有公司名的开头。
    2. {year_rule}
    3. 【年份隔离+标注】竞品数据里出现的任何年份都是【其他公司】的数据年份，绝对不能套用到本公司身上。禁止把竞品营收数值写成"本公司某年的营收"。★ 做横向对比时必须显式标注竞品数据年份：如果竞品年份不是「{period_label}」，要写明"竞品为202X年数据，与本公司{period_label}不完全同期"，禁止把旧年份数据当作同期直接对比。
    4. 【只用给定数据】本公司只使用上面【自身数据】给出的营收和增长率，不要编造本公司其他年份的历史营收。
    5. 客观评价营收表现，结合竞品做横向对比（对比时用「竞品XX表现如何，本公司如何」的并列句式，不要跨年拼接数字）。
    6. 必须结合【合规法条参考】，提示该公司的潜在财务或信息披露风险。
    7. 结合当前公司的具体财务异常点（如营收下降、净利润波动等），从法条中选择最相关的 1-2 条针对性点评，不要生搬硬套、不要每次都报同样的法条。
    """
    response = llm.invoke(prompt)
    return {"final_summary": response.content}


def save_to_db_node(state: AgentState):
    print("--> [节点5] 正在将研报写入 PostgreSQL 数据库存档...")
    metrics = state["metrics"]
    # 数据库密码从 .env 读取，避免明文硬编码泄露
    db_password = os.getenv("POSTGRES_PASSWORD", "")
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", "5433")
    db_name = os.getenv("POSTGRES_DB", "eduagent")
    db_user = os.getenv("POSTGRES_USER", "eduagent_user")
    DB_URI = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    try:
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                insert_sql = """
                    INSERT INTO investment_reports 
                    (company_name, industry, revenue_current, net_profit, growth_rate, competitor_info, final_summary, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cur.execute(insert_sql, (
                    metrics['company_name'], metrics['industry'], metrics['revenue_current'],
                    metrics['net_profit'], state["growth_rate"], state["competitor_info"], state["final_summary"],
        state.get("user_id", 0)
                ))
        print("    ✅ [存档成功] 研报已安全存入数据库！")
    except Exception as e:
        print(f"    ❌ [存档失败] 数据库写入报错: {e}")
    return {}