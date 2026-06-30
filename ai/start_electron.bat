@echo off
cd /d "%~dp0"

:: Check if backend is already running
netstat -an | find ":9528" | find "LISTENING" >nul 2>&1
if errorlevel 1 goto start_backend

echo Backend already running on port 9528, skipping...
goto start_electron

:start_backend
:: Kill stale service processes
for %%p in (8000 8020 8030 8040 8050) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| find ":%%p" ^| find "LISTENING"') do (
        echo Killing old service on port %%p PID=%%a
        taskkill /F /PID %%a >nul 2>&1
    )
)
timeout /t 1 /nobreak >nul

echo Starting Monika Live2D + Electron Desktop Pet...
echo.

:: Start backend in a new window (minimized)
start "Monika Backend" /min C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe scripts\start_bridge.py --no-browser

:: Wait for backend to be ready
echo Waiting for backend on port 9528...
:waitloop
timeout /t 1 /nobreak >nul
netstat -an | find ":9528" | find "LISTENING" >nul 2>&1
if errorlevel 1 goto waitloop

echo Backend is ready!
goto start_electron

:start_electron
echo Starting Electron app...
echo.

:: Launch Electron dev server
cd /d "%~dp0frontend\src"
start "Electron App" npm run dev

echo.
echo Electron window should open shortly.
echo Do NOT open http://localhost:5173/ in browser - it's Electron internal only.
echo.
echo Close this window to stop.
pause
