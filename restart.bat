@echo off
echo ==========================================
echo   MusicFlow Restart Script
echo ==========================================
echo.

echo Stopping existing services...
taskkill /F /IM python.exe
taskkill /F /IM pythonw.exe
taskkill /F /IM node.exe

echo Waiting for ports to release...
timeout /t 5 /nobreak >nul

echo Starting backend service...
cd /d D:\Documents\AI\MusicFlow\backend
start /B python -m uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload
timeout /t 3 /nobreak >nul

echo Starting frontend service...
cd /d D:\Documents\AI\MusicFlow\frontend
start /B npm run dev
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
echo Press any key to exit...
pause >nul
