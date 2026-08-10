@echo off
echo ==========================================
echo   MusicFlow Stop Script
echo ==========================================
echo.

echo Stopping Python processes...
taskkill /F /IM python.exe 2>nul

echo Stopping Node.js processes...
taskkill /F /IM node.exe 2>nul

timeout /t 2 /nobreak >nul

echo.
echo ==========================================
echo   All services stopped!
echo ==========================================
echo.
echo Press any key to exit...
pause >nul
