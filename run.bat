@echo off
echo ==========================================
echo   PC Remote Controller - Starting...
echo ==========================================
echo.
echo Your PC will be accessible from your phone
echo.

REM Get the computer's IP address
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set IP=%%a
    goto :found
)
:found
set IP=%IP: =%

echo Starting server...
echo.
echo ==========================================
echo   OPEN THIS URL ON YOUR PHONE:
echo   http://%IP%:8080
echo ==========================================
echo.

python -m backend.main

pause
