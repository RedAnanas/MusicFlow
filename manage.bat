@echo off
REM MusicFlow 综合管理脚本
REM 支持启动、停止、重启、查看状态等操作

:menu
cls
echo ==========================================
echo   MusicFlow 项目管理
echo ==========================================
echo.
echo  1. 启动项目
echo  2. 停止项目
echo  3. 重启项目
echo  4. 查看服务状态
echo  5. 查看日志
echo  6. 退出
echo.
set /p choice="请选择操作 (1-6): "

if "%choice%"=="1" goto start
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto restart
if "%choice%"=="4" goto status
if "%choice%"=="5" goto logs
if "%choice%"=="6" goto exit
echo 无效选择，请重试
timeout /t 2 /nobreak >nul
goto menu

:start
echo.
echo 启动 MusicFlow...
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
echo   MusicFlow 已启动！
echo ==========================================
echo.
echo 访问地址：
echo   前端：http://localhost:3000
echo   后端：http://localhost:8082
echo   API 文档：http://localhost:8082/docs
echo.
pause
goto menu

:stop
echo.
echo 停止 MusicFlow...
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
pause
goto menu

:restart
echo.
echo 重启 MusicFlow...
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
pause
goto menu

:status
echo.
echo ==========================================
echo   服务状态
echo ==========================================
echo.

echo 检查 Python 进程...
tasklist /FI "IMAGENAME eq python.exe" 2>nul | find /I "python.exe"
if errorlevel 1 (
    echo   Python: 未运行
) else (
    echo   Python: 运行中
)

echo.
echo 检查 Node.js 进程...
tasklist /FI "IMAGENAME eq node.exe" 2>nul | find /I "node.exe"
if errorlevel 1 (
    echo   Node.js: 未运行
) else (
    echo   Node.js: 运行中
)

echo.
echo 检查端口 8082...
netstat -an | find "8082" | find "LISTENING"
if errorlevel 1 (
    echo   端口 8082: 未监听
) else (
    echo   端口 8082: 已监听
)

echo.
echo 检查端口 3000...
netstat -an | find "3000" | find "LISTENING"
if errorlevel 1 (
    echo   端口 3000: 未监听
) else (
    echo   端口 3000: 已监听
)

echo.
pause
goto menu

:logs
echo.
echo ==========================================
echo   查看日志
echo ==========================================
echo.
echo 后端日志位置：
echo   D:\Documents\AI\MusicFlow\backend\logs\app.log
echo.
echo 前端日志位置：
echo   运行时在终端显示
echo.
echo 按任意键打开后端日志...
pause >nul
notepad "D:\Documents\AI\MusicFlow\backend\logs\app.log"
goto menu

:exit
echo.
echo 退出 MusicFlow 管理工具
exit
