@echo off
setlocal enabledelayedexpansion
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

REM Pick the LAN address specifically. The old code took the FIRST IPv4 from
REM ipconfig, which is often the Tailscale 100.x address - so it advertised a URL
REM that only works over the VPN.
set LANIP=
set TSIP=
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set "ADDR=%%a"
    set "ADDR=!ADDR: =!"
    if "!ADDR:~0,4!"=="192." (
        if not defined LANIP set "LANIP=!ADDR!"
    ) else if "!ADDR:~0,4!"=="100." (
        if not defined TSIP set "TSIP=!ADDR!"
    ) else if "!ADDR:~0,3!"=="10." (
        if not defined LANIP set "LANIP=!ADDR!"
    )
)

echo   OPEN ON YOUR PHONE:
if defined LANIP echo     Home WiFi:  http://!LANIP!:8080
if defined TSIP  echo     Tailscale:  http://!TSIP!:8080   (needs the Tailscale app)
echo     Anywhere:   see the PUBLIC URL below if the tunnel is on
echo.
echo   Press Ctrl+C to stop.
echo ==========================================
echo.

.venv\Scripts\python.exe -m backend.main

pause
