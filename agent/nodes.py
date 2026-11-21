import os
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
    return {"metrics": metrics}


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
    query = f"{company} 所在的 {industry} 行业 2025年 主要竞争对手 营收对比"
    print(f"    [动态搜索词]: {query}")

    search_results = search_tool.invoke(query)
    competitor_text = ""
    if isinstance(search_results, str):
        competitor_text = search_results
    elif isinstance(search_results, list):
        for result in search_results:
            if isinstance(result, dict):
                content = result.get('content', result.get('snippet', str(result)))
                competitor_text += f"内容：{content}\n\n"
            else:
                competitor_text += f"内容：{str(result)}\n\n"
    print(f"    [搜索完成] 抓取到约 {len(competitor_text)} 个字符的同行数据。")
    return {"competitor_info": competitor_text}


def retrieve_compliance_node(state: AgentState):
    print("--> [节点3.5] 正在检索 Milvus 合规知识库 (RAG)...")
    company = state["metrics"].get("company_name", "未知公司")
    industry = state["metrics"].get("industry", "未知行业")

    # 拼装一个复合查询，让向量库去找相关的法条
    query = f"{company} {industry} 行业 财务合规 信息披露 风险"
    print(f"    [RAG查询词]: {query}")

    # 去 Milvus 里搜最相关的 2 条法条
    docs = vectorstore.similarity_search(query, k=2)
    rules = "\n".join([doc.page_content for doc in docs])

    print(f"    [检索完成] 命中 {len(docs)} 条合规条款。")
    return {"compliance_rules": rules}


def summary_node(state: AgentState):
    print("--> [节点4] 正在综合自身数据与竞品数据，生成对比研报...")
    metrics = state["metrics"]
    prompt = f"""
    你是一个资深金融投资与合规顾问。请根据以下数据，撰写一段财报分析摘要（约200字）：

    【自身数据】
    公司：{metrics['company_name']} ({metrics['industry']})
    营收：{metrics['revenue_current']} 亿元，同比增长：{state['growth_rate']}%

    【竞品数据】
    {state['competitor_info']}

    【合规法条参考 (RAG检索)】 
    {state.get('compliance_rules', '无相关法条')}

    要求：
    1. 客观评价营收表现。
    2. 结合竞品做横向对比。
    3. 必须结合【合规法条参考】，提示该公司的潜在财务或信息披露风险。
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