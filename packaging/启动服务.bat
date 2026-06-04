@echo off
chcp 65001 >nul 2>&1
title InsightClass Web 服务

echo ========================================
echo   InsightClass Web 推理服务
echo ========================================
echo.
echo 启动中...
echo 浏览器访问: http://localhost:8000
echo 按 Ctrl+C 停止服务
echo.

InsightClass.exe serve --port 8000

pause
