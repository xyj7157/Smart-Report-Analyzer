from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from celery.result import AsyncResult
import os
import shutil
from tasks import analyze_report_task, celery_app
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="财报智能分析 API ")

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

    # 1. 把文件保存到本地临时目录
    temp_file_path = f"temp_{file.filename}"
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. 扔进 Celery 异步队列，立刻返回任务 ID！
    task = analyze_report_task.delay(temp_file_path)
    return {"task_id": task.id, "status": "processing", "message": "任务已提交，AI 正在后台处理..."}


@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    # 查询任务状态
    task_result = AsyncResult(task_id, app=celery_app)

    if task_result.state == 'PENDING':
        return {"status": "pending", "message": "排队中或等待执行..."}
    elif task_result.state == 'STARTED':
        return {"status": "started", "message": "AI 正在解析与生成研报..."}
    elif task_result.state == 'SUCCESS':
        return {"status": "success", "result": task_result.result}
    else:
        return {"status": "failed", "message": str(task_result.info)}