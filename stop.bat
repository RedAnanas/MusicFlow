@echo off
REM MusicFlow 停止脚本
REM 用于停止所有服务

echo ==========================================
echo   MusicFlow 停止脚本
echo ==========================================
echo.

echo 停止 Python 进程...
taskkill /F /IM python.exe 2>nul

echo 停止 Node.js 进程...
taskkill /F /IM node.exe 2>nul

timeout /t 2 /nobreak >nul

echo.
echo ==========================================
echo   所有服务已停止！
echo ==========================================
echo.
echo 按任意键退出...
pause >nul
