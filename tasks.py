import os
import shutil
import json
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# 初始化 Celery，连接本地的 Redis (broker)
celery_app = Celery('report_tasks', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

from agent.graph import agent_graph
from core.pdf_parser import read_pdf_text


@celery_app.task(bind=True)
def analyze_report_task(self, file_path: str, user_id: int):
    """
    异步处理财报的后台任务
    """
    print(f"[Task {self.request.id}] 开始处理文件: {file_path}")
    try:
        # 1. 解析 PDF
        raw_text = read_pdf_text(file_path)
        initial_state = {"raw_text": raw_text, "user_id": user_id}

        # 2. 跑 LangGraph（注：在后台任务里，我们直接通过 invoke 同步获取最终结果）
        # 如果你需要前端看到进度，可以在这里分阶段更新 self.update_state
        final_state = agent_graph.invoke(initial_state)

        # 3. 提取返回结果
        metrics = final_state.get("metrics", {})
        result = {
            "status": "success",
            "company_name": metrics.get("company_name", ""),
            "industry": metrics.get("industry", ""),
            "revenue_current": metrics.get("revenue_current", 0),
            "revenue_previous": metrics.get("revenue_previous", 0),
            "net_profit": metrics.get("net_profit", 0),
            "growth_rate": final_state.get("growth_rate", 0),
            "summary": final_state.get("final_summary", "")
        }
        print(f"[Task {self.request.id}] 处理完成！")
        return result

    except Exception as e:
        print(f"[Task {self.request.id}] 报错: {e}")
        raise e
    finally:
        # 清理临时文件
        if os.path.exists(file_path):
            os.remove(file_path)