@echo off
chcp 65001 >nul
title 财报分析系统 - 一键启动
cd /d D:\develop\Smart-Report-Analyzer

set PY=D:\develop\anaconda\envs\new_agent\python.exe

echo ========================================
echo   财报分析系统  一键启动
echo ========================================
echo.

echo [1/4] 启动 Docker 基建（Milvus / Redis / Postgres）
docker stop report-frontend >nul 2>&1
docker start milvus-etcd >nul 2>&1
docker start milvus-minio >nul 2>&1
docker start milvus-standalone >nul 2>&1
docker start redis-celery >nul 2>&1
docker start edu_agent_postgres >nul 2>&1
echo       Docker 基建已就绪，等待 8 秒...
timeout /t 8 /nobreak >nul

echo [2/4] 启动 Celery 后台打工人（新窗口）
start "Celery-Worker" cmd /k "title Celery-Worker && "%PY%" -m celery -A tasks.celery_app worker --loglevel=info --pool=solo"

echo [3/4] 启动 FastAPI 后端（新窗口）
start "FastAPI" cmd /k "title FastAPI && "%PY%" -m uvicorn api:app --reload"
echo       等待后端就绪 6 秒...
timeout /t 6 /nobreak >nul

echo [4/4] 启动 Streamlit 前端（新窗口）
start "Streamlit" cmd /k "title Streamlit && "%PY%" -m streamlit run frontend.py"

echo.
echo ========================================
echo   全部启动完成！
echo   浏览器访问: http://localhost:8501
echo.
echo   现在会弹出 3 个新窗口:
echo     Celery-Worker  = 后台打工人
echo     FastAPI        = 后端接口
echo     Streamlit      = 前端网页
echo   关闭服务: 运行「一键关闭.bat」或直接关掉这 3 个窗口
echo ========================================
echo.
pause
