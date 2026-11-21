# 📊 智能财报分析系统 (Full-Stack AI Agent)

基于 LangGraph + FastAPI + Streamlit + PostgreSQL 构建的全栈 AI 财报分析系统。上传财报 PDF，系统将自动提取核心指标、联网搜索竞品数据，并生成带图表的专业投资研报。

## 🚀 核心功能
- **多模态文档解析**：基于 `pdfplumber` 提取长篇幅财报核心数据。
- **AI 智能体编排**：基于 LangGraph 构建 `提取 -> 计算 -> 搜索 -> 总结 -> 落库` 五节点流水线。
- **外部工具调用**：结合 Tavily Search 实时抓取同行业竞品数据，实现横向对比。
- **高可靠校验**：结合 Pydantic 强约束与 Python 原生计算，杜绝大模型幻觉。
- **全栈前后端分离**：FastAPI 提供高性能异步 API，Streamlit 构建交互式图表看板。
- **数据持久化**：解析结果与研报自动存入 PostgreSQL 数据库。

## 🛠️ 技术栈
`Python` | `LangChain` | `LangGraph` | `DeepSeek` | `FastAPI` | `Streamlit` | `PostgreSQL` | `Plotly`
## 🚀 核心功能演示
![系统演示截图](assets/demo.png)

### 💡 RAG 知识库增强
结合 **Milvus 向量数据库**与 **BGE 中文词向量模型**，将私有合规法条（如《上市公司信息披露管理办法》）嵌入大模型推理链路，实现财报数据与法规条款的交叉验证，自动生成合规风险提示。
## 🏃 快速启动
1. 克隆仓库并安装依赖：`pip install -r requirements.txt`
2. 配置 `.env` 文件（填入 `DEEPSEEK_API_KEY`, `TAVILY_API_KEY` 及数据库连接串）。
3. 启动后端：`python -m uvicorn api:app --reload`
4. 启动前端：`streamlit run frontend.py`