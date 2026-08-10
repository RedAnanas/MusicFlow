@echo off
echo ==========================================
echo   MusicFlow Start Script
echo ==========================================
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
echo Press any key to exit...
pause >nul
