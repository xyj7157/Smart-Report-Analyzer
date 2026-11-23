from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from celery.result import AsyncResult
import os
import shutil
from pydantic import BaseModel
from tasks import analyze_report_task, celery_app
from auth import register_user, authenticate_user, decode_token
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="财报智能分析 API (多用户版)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth2 方案（主要用于生成 API 文档里的锁图标）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# ===== 请求体模型 =====
class RegisterReq(BaseModel):
    username: str
    password: str


class LoginReq(BaseModel):
    username: str
    password: str


# ===== 从 token 里解析当前用户 =====
def get_current_user(authorization: str = Header(None)):
    """前端在 Header 里带 Authorization: Bearer <token>"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供有效的登录凭证")
    token = authorization.split("Bearer ")[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期或凭证无效，请重新登录")
    return payload


# ===== 认证接口 =====
@app.post("/register")
def register(req: RegisterReq):
    ok, msg = register_user(req.username, req.password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg, "username": req.username}


@app.post("/login")
def login(req: LoginReq):
    result = authenticate_user(req.username, req.password)
    if not result:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return result  # {user_id, username, token}


# ===== 业务接口（现在需要登录了）=====
@app.post("/analyze")
async def analyze_report(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只能上传 PDF 文件！")

    # 1. 保存临时文件（文件名带上 user_id，避免多人文件重名冲突）
    temp_file_path = f"temp_u{current_user['user_id']}_{file.filename}"
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. 把 user_id 一起传给 Celery 任务
    task = analyze_report_task.delay(temp_file_path, current_user["user_id"])
    return {
        "task_id": task.id,
        "status": "processing",
        "message": f"任务已提交，AI 正在后台处理（用户: {current_user['username']}）",
    }


@app.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    task_result = AsyncResult(task_id, app=celery_app)

    if task_result.state == "PENDING":
        return {"status": "pending", "message": "排队中或等待执行..."}
    elif task_result.state == "STARTED":
        return {"status": "started", "message": "AI 正在解析与生成研报..."}
    elif task_result.state == "SUCCESS":
        return {"status": "success", "result": task_result.result}
    else:
        return {"status": "failed", "message": str(task_result.info)}

@app.get("/my-reports")
def my_reports(current_user: dict = Depends(get_current_user)):
    """返回当前用户自己的研报列表"""
    import psycopg
    from dotenv import load_dotenv
    load_dotenv()
    DB_URI = (
        f"postgresql://{os.getenv('POSTGRES_USER', 'eduagent_user')}:"
        f"{os.getenv('POSTGRES_PASSWORD')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5433')}/"
        f"{os.getenv('POSTGRES_DB', 'eduagent')}"
    )
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT company_name, industry, revenue_current, net_profit,
                       growth_rate, final_summary, created_at
                FROM investment_reports
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT 20
                """,
                (current_user["user_id"],),  # 👈 关键：只查当前用户的
            )
            rows = cur.fetchall()
    return [
        {
            "company_name": r[0], "industry": r[1],
            "revenue_current": r[2], "net_profit": r[3],
            "growth_rate": r[4], "summary": r[5],
            "created_at": str(r[6]) if r[6] else "",
        }
        for r in rows
    ]
