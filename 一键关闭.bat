@echo off
title Report Analyzer - STOP
echo Stopping Celery / FastAPI / Streamlit windows...
taskkill /FI "WINDOWTITLE eq Celery-Worker*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq FastAPI*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit*" /F >nul 2>&1
echo.
echo STOPPED.
echo Docker services (Milvus / Redis / Postgres) stay running.
echo Next START will reuse them.
echo.
pause
