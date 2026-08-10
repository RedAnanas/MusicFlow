@echo off
REM MusicFlow 启动脚本
REM 用于启动后端和前端服务

echo ==========================================
echo   MusicFlow 启动脚本
echo ==========================================
echo.

REM 停止现有服务
echo 停止现有服务...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM node.exe 2>nul
timeout /t 2 /nobreak >nul

REM 启动后端
echo 启动后端服务...
cd /d D:\Documents\AI\MusicFlow\backend
start "MusicFlow Backend" python -m uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload
timeout /t 3 /nobreak >nul

REM 启动前端
echo 启动前端服务...
cd /d D:\Documents\AI\MusicFlow\frontend
start "MusicFlow Frontend" npm run dev
timeout /t 3 /nobreak >nul

echo.
echo ==========================================
echo   MusicFlow 已启动！
echo ==========================================
echo.
echo 访问地址：
echo   前端：http://localhost:3000
echo   后端：http://localhost:8082
echo   API 文档：http://localhost:8082/docs
echo.
echo 按任意键退出...
pause >nul
