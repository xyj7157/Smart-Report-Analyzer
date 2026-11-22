from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import os
import shutil
import json
from dotenv import load_dotenv

load_dotenv()

from agent.graph import agent_graph
from core.pdf_parser import read_pdf_text

app = FastAPI(title="财报智能分析 API", description="上传PDF，返回专业研报")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/analyze")
async def analyze_report(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只能上传 PDF 文件！")

    print(f"接收到文件: {file.filename}")
    temp_file_path = f"temp_{file.filename}"

    try:
        # 1. 保存并解析 PDF
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        raw_text = read_pdf_text(temp_file_path)
        initial_state = {"raw_text": raw_text}

        # 2. 定义流式生成器
        async def event_generator():
            final_state = {}
            try:
                # 使用 astream_events 监听 LangGraph 的每一步
                async for event in agent_graph.astream_events(initial_state, version="v2"):
                    kind = event["event"]

                    # ① 拦截大模型的流式输出（只流式输出 summary 节点的内容）
                    if kind == "on_chat_model_stream":
                        if event["metadata"].get("langgraph_node") == "summary":
                            chunk = event["data"]["chunk"]
                            if chunk.content:
                                # 通过 SSE 协议发给前端
                                yield f"data: {json.dumps({'type': 'text', 'content': chunk.content})}\n\n"

                    # ② 收集各个节点的状态输出，方便最后发给前端画图
                    elif kind == "on_chain_end":
                        if event["name"] in ["extract", "calculate", "search_competitor", "retrieve_compliance", "summary", "save_to_db"]:
                            node_output = event["data"].get("output", {})
                            if isinstance(node_output, dict):
                                final_state.update(node_output)

                # ③ 图全部跑完后，发送图表所需的元数据 (Metadata)
                metrics = final_state.get("metrics", {})
                metadata = {
                    "company_name": metrics.get("company_name", ""),
                    "industry": metrics.get("industry", ""),
                    "revenue_current": metrics.get("revenue_current", 0),
                    "revenue_previous": metrics.get("revenue_previous", 0),
                    "net_profit": metrics.get("net_profit", 0),
                    "growth_rate": final_state.get("growth_rate", 0),
                }
                yield f"data: {json.dumps({'type': 'metadata', 'data': metadata})}\n\n"

            except Exception as e:
                print(f"流式处理失败: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            finally:
                # 清理临时文件
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                    print("临时文件已清理。")

        # 3. 返回 SSE 流
        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        print(f"处理失败: {e}")
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"AI 处理失败: {str(e)}")