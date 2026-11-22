import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_OFFLINE"] = "1"


import os
import re
import json
import psycopg
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

    # 从财报原文提取报告期年份（前20页里的“2025年年度报告”），作为权威年份
    year_match = re.search(r"(20\d{2})\s*年\s*年度报告", state["raw_text"][:3000])
    report_year = year_match.group(1) if year_match else ""
    print(f"    [报告期年份]: {report_year or '未识别，将由模型自行描述'}")

    return {"metrics": metrics, "report_year": report_year}


def calculate_node(state: AgentState):
    print("--> [节点2] 正在计算同比增长率...")
    metrics = state["metrics"]
    current = metrics["revenue_current"]
    previous = metrics["revenue_previous"]
    growth = ((current - previous) / previous) * 100 if previous != 0 else 0.0
    print(f"    [计算结果] 营收增长率: {growth:.2f}%")
    return {"growth_rate": round(growth, 2)}


def search_competitor_node(state: AgentState):
    print("--> [节点3] 正在呼叫 Tavily 联网搜索同行业竞品数据...")
    company = state["metrics"].get("company_name", "未知公司")
    industry = state["metrics"].get("industry", "同行业")

    # 1. 精简搜索词，提高搜索成功率
    query = f"{company} 行业 竞争对手 营收对比"
    print(f"    [动态搜索词]: {query}")

    try:
        # 2. 给 Tavily 加个重试机制，防止瞬时并发失败
        search_results = search_tool.invoke(query)
        competitor_text = ""

        # 3. 防御性解析（兼容字符串、列表、字典等所有恶心格式）
        if isinstance(search_results, str):
            competitor_text = search_results
        elif isinstance(search_results, list):
            for result in search_results:
                if isinstance(result, dict):
                    content = result.get('content', result.get('snippet', ''))
                    if content:
                        competitor_text += f"内容：{content}\n\n"
                elif isinstance(result, str):
                    competitor_text += f"内容：{result}\n\n"
        else:
            competitor_text = str(search_results)

        # 4. 如果搜出来是空的，给个大模型能看懂的提示
        if len(competitor_text.strip()) < 10:
            print("    ⚠️ [警告] Tavily 搜索返回空数据（可能是并发限流或网络波动）。")
            competitor_text = "当前网络未检索到有效的竞品数据，请直接根据行业常识进行简要对比。"

        print(f"    [搜索完成] 抓取到约 {len(competitor_text)} 个字符的同行数据。")
        return {"competitor_info": competitor_text}

    except Exception as e:
        print(f"    ❌ [搜索报错] Tavily 搜索失败: {e}")
        # 哪怕报错了，也不能让整个图崩溃，给个兜底数据
        return {"competitor_info": "由于网络原因，未能获取到竞品数据，请基于自身财务表现进行分析。"}


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

    # 年份口径：以财报原文识别的年份为准，禁止模型自行推断
    if report_year:
        year_rule = (
            f"★ 年份口径（强制）：本次分析的财报为【{report_year}年年度报告】。"
            f"描述本公司数据时只能使用「{report_year}年」「本期」「上期」这类表述，"
            f"绝对禁止把年份写成其他数字（如{int(report_year)-1}年、{int(report_year)-2}年）。"
        )
    else:
        year_rule = "★ 年份口径（强制）：无法确定报告年份，描述本公司时只用「本期」「上期」，禁止编造任何具体年份数字。"

    prompt = f"""
    你是一个资深金融投资与合规顾问。请根据以下数据，撰写一段财报分析摘要（约200字）。

    【本公司名称】{company}
    【自身数据】
    公司：{company} ({metrics['industry']})
    营收：{metrics['revenue_current']} 亿元，同比增长：{state['growth_rate']}%

    【竞品数据】（注意：这里面出现的年份和数值都是其他公司的，仅用于横向对比）
    {state['competitor_info']}

    【合规法条参考 (RAG检索)】
    {state.get('compliance_rules', '无相关法条')}

    ★★★ 输出规则（必须严格遵守，违反视为错误）★★★
    1. 【开头强制】摘要第一句必须以公司全称开头，格式为「{company}本期营收…」或「{company}202X年营收…」。禁止省略公司名，禁止只写「本期营收」「财报分析摘要」这类没有公司名的开头。
    2. {year_rule}
    3. 【年份隔离】竞品数据里出现的任何年份（如2023年、2024年）都是【其他公司】的数据年份，绝对不能套用到本公司身上。禁止把竞品的营收数值（如1505.6亿）写成"本公司某年的营收"，禁止拿竞品数值和本公司营收做跨年份的增减对比。
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
    # ⚠️ 换成你真实的密码
    DB_URI = "postgresql://eduagent_user:123456@localhost:5433/eduagent"
    try:
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                insert_sql = """
                    INSERT INTO investment_reports 
                    (company_name, industry, revenue_current, net_profit, growth_rate, competitor_info, final_summary)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cur.execute(insert_sql, (
                    metrics['company_name'], metrics['industry'], metrics['revenue_current'],
                    metrics['net_profit'], state["growth_rate"], state["competitor_info"], state["final_summary"]
                ))
        print("    ✅ [存档成功] 研报已安全存入数据库！")
    except Exception as e:
        print(f"    ❌ [存档失败] 数据库写入报错: {e}")
    return {}