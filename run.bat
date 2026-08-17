@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Not set up yet. Run setup.bat first.
    pause
    exit /b 1
)

echo ==========================================
echo   PC Remote Controller - Starting...
echo ==========================================
echo.

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set IP=%%a
    goto :found
)
:found
set IP=%IP: =%

echo   OPEN THIS URL ON YOUR PHONE:
echo   http://%IP%:8080
echo.
echo   Press Ctrl+C to stop.
echo ==========================================
echo.

.venv\Scripts\python.exe -m backend.main

pause
