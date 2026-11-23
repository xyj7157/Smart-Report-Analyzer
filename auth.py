"""JWT 认证模块：密码哈希、token 生成与校验、注册登录"""
# ===== bcrypt 4.x 兼容补丁：让 passlib 能读到版本号，消除警告 =====
import bcrypt
if not hasattr(bcrypt, "__about__"):
    class _BcryptAbout:
        __version__ = getattr(bcrypt, "__&#8203;version__", "4.0.0")
    bcrypt.__about__ = _BcryptAbout()
# ================================================================
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import psycopg
from passlib.context import CryptContext
from jose import JWTError, jwt

load_dotenv()

# 数据库 URI（跟 nodes.py 保持一致，从 .env 读取）
DB_URI = (
    f"postgresql://{os.getenv('POSTGRES_USER', 'eduagent_user')}:"
    f"{os.getenv('POSTGRES_PASSWORD')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5433')}/"
    f"{os.getenv('POSTGRES_DB', 'eduagent')}"
)

# JWT 配置
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-me")
ALGORITHM = "HS256"
EXPIRE_HOURS = 24 * 7  # token 7 天有效

# 密码哈希工具（bcrypt 是目前最主流的密码加密算法）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """把明文密码加密成哈希，绝不存明文"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码和哈希是否匹配"""
    return pwd_context.verify(plain, hashed)


def create_token(user_id: int, username: str) -> str:
    """生成 JWT token（相当于用户的电子身份证）"""
    expire = datetime.utcnow() + timedelta(hours=EXPIRE_HOURS)
    payload = {"sub": str(user_id), "name": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    """校验 token，成功返回 {user_id, username}，失败返回 None"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {"user_id": int(payload["sub"]), "username": payload.get("name", "")}
    except JWTError:
        return None


def register_user(username: str, password: str):
    """注册新用户，返回 (是否成功, 提示信息)"""
    if not username or not password:
        return False, "用户名或密码不能为空"
    if len(password) < 6:
        return False, "密码至少 6 位"
    try:
        hashed = hash_password(password)
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO report_users (username, hashed_password) VALUES (%s, %s)",
                    (username, hashed),
                )
        return True, "注册成功"
    except psycopg.errors.UniqueViolation:
        return False, "用户名已存在"
    except Exception as e:
        return False, f"注册失败: {e}"


def authenticate_user(username: str, password: str):
    """登录校验，成功返回 {user_id, username, token}，失败返回 None"""
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, hashed_password FROM report_users WHERE username = %s", (username,)
            )
            row = cur.fetchone()

    if not row:
        return None
    user_id, hashed = row
    if not verify_password(password, hashed):
        return None

    token = create_token(user_id, username)
    return {"user_id": user_id, "username": username, "token": token}
