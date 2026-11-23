"""初始化财报项目专用用户表 report_users（绝不触碰教育项目的 users 表）"""
import os
from dotenv import load_dotenv
load_dotenv()
import psycopg

uri = (
    f"postgresql://{os.getenv('POSTGRES_USER', 'eduagent_user')}:"
    f"{os.getenv('POSTGRES_PASSWORD')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5433')}/"
    f"{os.getenv('POSTGRES_DB', 'eduagent')}"
)

with psycopg.connect(uri, autocommit=True) as conn:
    with conn.cursor() as cur:
        # 财报项目专用表，加 report_ 前缀，避免和教育项目的 users 冲突
        cur.execute("""
            CREATE TABLE IF NOT EXISTS report_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ report_users 表已就绪")

        # investment_reports.user_id 上次已加过，确保一下
        cur.execute("""
            ALTER TABLE investment_reports
            ADD COLUMN IF NOT EXISTS user_id INTEGER
        """)
        print("✅ investment_reports.user_id 字段已就绪")

        cur.execute("SELECT COUNT(*) FROM report_users")
        print(f"   财报项目用户数: {cur.fetchone()[0]}")
