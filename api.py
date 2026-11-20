from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import shutil

from dotenv import load_dotenv
load_dotenv() # 必须提前加载环境变量

from agent.graph import agent_graph
from core.pdf_parser import read_pdf_text

# 1. 初始化 FastAPI 应用
app = FastAPI(title="财报智能分析 API", description="上传PDF，返回专业研报")

# 允许跨域（方便以后前端网页调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. 定义返回的数据格式（这就是前端能直接用的 JSON 格式）
class ReportResponse(BaseModel):
    status: str
    company_name: str
    industry: str
    growth_rate: float
    revenue_current: float  # 👈 新增：本期营收
    revenue_previous: float  # 👈 新增：上期营收
    net_profit: float  # 👈 新增：净利润
    summary: str


# 3. 编写核心 API 接口
@app.post("/analyze", response_model=ReportResponse)
async def analyze_report(file: UploadFile = File(...)):
    # 检查文件类型
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只能上传 PDF 文件！")

    print(f"接收到文件: {file.filename}")

    # 把用户上传的文件临时存到本地
    temp_file_path = f"temp_{file.filename}"
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 🚀 第一步：解析 PDF
        raw_text = read_pdf_text(temp_file_path)

        # 🚀 第二步：把文本扔进 LangGraph 流水线！
        # 注意：因为流水线里有数据库写入节点，跑完后数据库里就会多一条记录
        initial_state = {"raw_text": raw_text}

        # 执行图（获取最终结果）
        final_state = agent_graph.invoke(initial_state)

        # 🚀 第三步：组装结果返回给前端
        metrics = final_state["metrics"]
        return ReportResponse(
            status="success",
            company_name=metrics.get("company_name", "未知公司"),
            industry=metrics.get("industry", "未知行业"),
            revenue_current=metrics.get("revenue_current", 0.0),  # 👈 加上 .get
            revenue_previous=metrics.get("revenue_previous", 0.0),  # 👈 加上 .get
            net_profit=metrics.get("net_profit", 0.0),  # 👈 加上 .get
            growth_rate=final_state.get("growth_rate", 0.0),
            summary=final_state.get("final_summary", "暂无总结")
        )

    except Exception as e:
        print(f"处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"AI 处理失败: {str(e)}")

    finally:
        # 🧹 清理临时文件
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            print("临时文件已清理。")


# 4. 启动服务（如果你直接运行这个文件的话）
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)