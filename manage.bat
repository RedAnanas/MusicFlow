@echo off
:menu
cls
echo ==========================================
echo   MusicFlow Management
echo ==========================================
echo.
echo  1. Start Project
echo  2. Stop Project
echo  3. Restart Project
echo  4. Exit
echo.
set /p choice="Select option (1-4): "

if "%choice%"=="1" goto start
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto restart
if "%choice%"=="4" goto exit
echo Invalid option, try again
timeout /t 2 /nobreak >nul
goto menu

:start
echo.
echo Starting MusicFlow...
echo.

echo Stopping existing services...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul
taskkill /F /IM node.exe 2>nul
timeout /t 2 /nobreak >nul

echo Starting backend service (background)...
cd /d D:\Documents\AI\MusicFlow\backend
start "" /B pythonw.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload
timeout /t 3 /nobreak >nul

echo Starting frontend service (background)...
cd /d D:\Documents\AI\MusicFlow\frontend
start "" /B npm run dev
timeout /t 3 /nobreak >nul

echo.
echo ==========================================
echo   MusicFlow Started!
echo ==========================================
echo.
echo Access URLs:
echo   Frontend: http://localhost:3000
echo   Backend:  http://localhost:8082
echo   API Docs: http://localhost:8082/docs
echo.
echo Services are running in background.
echo You can close this window safely.
echo.
pause
goto menu

:stop
echo.
echo Stopping MusicFlow...
echo.

echo Stopping Python processes...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul

echo Stopping Node.js processes...
taskkill /F /IM node.exe 2>nul

timeout /t 2 /nobreak >nul

echo.
echo ==========================================
echo   All services stopped!
echo ==========================================
echo.
pause
goto menu

:restart
echo.
echo Restarting MusicFlow...
echo.

echo Stopping existing services...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul
taskkill /F /IM node.exe 2>nul
timeout /t 2 /nobreak >nul

echo Starting backend service (background)...
cd /d D:\Documents\AI\MusicFlow\backend
start "" /B pythonw.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload
timeout /t 3 /nobreak >nul

echo Starting frontend service (background)...
cd /d D:\Documents\AI\MusicFlow\frontend
start "" /B npm run dev
timeout /t 3 /nobreak >nul

echo.
echo ==========================================
echo   MusicFlow Restarted!
echo ==========================================
echo.
echo Access URLs:
echo   Frontend: http://localhost:3000
echo   Backend:  http://localhost:8082
echo   API Docs: http://localhost:8082/docs
echo.
echo Services are running in background.
echo You can close this window safely.
echo.
pause
goto menu

:exit
echo.
echo Goodbye!
exit
