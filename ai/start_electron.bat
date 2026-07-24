@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%~dp0"
set "FRONTEND=%ROOT%frontend"
set "PYTHON=C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe"
set ELECTRON_RUN_AS_NODE=

echo ============================================
echo   Monika Companion - Electron Desktop
echo ============================================
echo.

echo [1/3] Stopping previous session...
set "ELECTRON_PID_FILE=%ROOT%data\pids\electron.pid"
if exist "%ELECTRON_PID_FILE%" (
    set /p OLD_ELECTRON_PID=<"%ELECTRON_PID_FILE%"
    if defined OLD_ELECTRON_PID taskkill /F /T /PID !OLD_ELECTRON_PID! >nul 2>&1
    del /q "%ELECTRON_PID_FILE%" >nul 2>&1
)
"%PYTHON%" scripts\lifecycle.py stop >nul 2>&1
for /f "usebackq" %%i in (`"%PYTHON%" scripts\_list_ports.py`) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| find ":%%i" ^| find "LISTENING" 2^>nul') do taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul
echo     Done.

echo [2/3] Building frontend...
cd /d "%FRONTEND%"
call node node_modules\vite\bin\vite.js build
if errorlevel 1 (
    echo [FAIL] Frontend build failed
    pause
    exit /b 1
)
echo     OK.

echo [3/3] Launching Electron...
cd /d "%FRONTEND%"
set NODE_ENV=production
node node_modules\electron\cli.js .

echo.
echo Companion closed. Cleaning up...
cd /d "%ROOT%"
"%PYTHON%" scripts\lifecycle.py stop >nul 2>&1
timeout /t 1 /nobreak >nul
echo Done.
pause
