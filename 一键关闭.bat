@echo off
chcp 65001 >nul
title 财报分析系统 - 一键关闭
echo 正在关闭 Celery / FastAPI / Streamlit 三个服务窗口...
taskkill /FI "WINDOWTITLE eq Celery-Worker*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq FastAPI*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit*" /F >nul 2>&1
echo.
echo 已关闭。
echo 提示: Docker 基建（Milvus / Redis / Postgres）保持运行即可，
echo       下次用「一键启动.bat」会直接复用，无需重开。
echo.
pause
