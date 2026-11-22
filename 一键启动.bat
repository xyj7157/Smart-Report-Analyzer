@echo off
title Report Analyzer - START
cd /d D:\develop\Smart-Report-Analyzer

set PY=D:\develop\anaconda\envs\new_agent\python.exe

echo ========================================
echo   Report Analyzer - START
echo ========================================
echo.

echo [1/4] Starting Docker services...
docker stop report-frontend >nul 2>&1
docker start milvus-etcd >nul 2>&1
docker start milvus-minio >nul 2>&1
docker start milvus-standalone >nul 2>&1
docker start redis-celery >nul 2>&1
docker start edu_agent_postgres >nul 2>&1
echo       Docker ready. Waiting 8 seconds...
timeout /t 8 /nobreak >nul

echo [2/4] Starting Celery worker (new window)...
start "Celery-Worker" cmd /k "title Celery-Worker && %PY% -m celery -A tasks.celery_app worker --loglevel=info --pool=solo"

echo [3/4] Starting FastAPI backend (new window)...
start "FastAPI" cmd /k "title FastAPI && %PY% -m uvicorn api:app --reload"
echo       Waiting 6 seconds...
timeout /t 6 /nobreak >nul

echo [4/4] Starting Streamlit frontend (new window)...
start "Streamlit" cmd /k "title Streamlit && %PY% -m streamlit run frontend.py"

echo.
echo ========================================
echo   DONE. Open http://localhost:8501
echo.
echo   3 windows opened:
echo     Celery-Worker  = background worker
echo     FastAPI        = backend API
echo     Streamlit      = frontend web
echo   To stop: run the STOP script, or close those 3 windows
echo ========================================
echo.
pause
