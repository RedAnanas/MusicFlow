@echo off
REM MusicFlow 重启脚本
REM 用于重启所有服务

echo ==========================================
echo   MusicFlow 重启脚本
echo ==========================================
echo.

echo 停止现有服务...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM node.exe 2>nul
timeout /t 2 /nobreak >nul

echo 启动后端服务...
cd /d D:\Documents\AI\MusicFlow\backend
start "MusicFlow Backend" python -m uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload
timeout /t 3 /nobreak >nul

echo 启动前端服务...
cd /d D:\Documents\AI\MusicFlow\frontend
start "MusicFlow Frontend" npm run dev
timeout /t 3 /nobreak >nul

echo.
echo ==========================================
echo   MusicFlow 已重启！
echo ==========================================
echo.
echo 访问地址：
echo   前端：http://localhost:3000
echo   后端：http://localhost:8082
echo   API 文档：http://localhost:8082/docs
echo.
echo 按任意键退出...
pause >nul
