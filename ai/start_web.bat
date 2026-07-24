@echo off
cd /d "%~dp0"
set "ROOT=%~dp0"
set "FRONTEND=%ROOT%frontend"
set "PYTHON=C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe"

echo ============================================
echo   Monika Companion - Web Browser
echo ============================================
echo.

echo [1/3] Stopping previous session...
"%PYTHON%" scripts\lifecycle.py stop >nul 2>&1
echo     Done.

echo [2/3] Building frontend...
cd /d "%FRONTEND%"
call node node_modules\vite\bin\vite.js build
if errorlevel 1 (
    echo [FAIL] Build failed
    pause
    exit /b 1
)
echo     OK.

echo [3/3] Starting services...
echo.
echo     Starting: ASR(9101) LLM(9102) TTS(9103) Memory(9104) GSVI(9105) Bridge(9528)
echo     GSVI loads Monika voice model (~20s, GPU)
echo     ASR  loads Qwen3-ASR 1.7B (~60s, GPU)
echo     Check logs\*.log for detailed progress
echo.
cd /d "%ROOT%"
start "Monika-Services" cmd /c "cd /d %ROOT% && %PYTHON% scripts\lifecycle.py start --mode backend"

echo     Waiting for all services...
echo     Bridge (9528) ...
for /L %%i in (1,1,20) do (
    timeout /t 2 /nobreak >nul
    netstat -an | find ":9528" | find "LISTENING" >nul 2>&1
    if not errorlevel 1 goto bridge_ok
)
echo     [WARN] Bridge timeout - services still loading
:bridge_ok

echo     TTS model (9103) ...
for /L %%i in (1,1,30) do (
    timeout /t 2 /nobreak >nul
    "%PYTHON%" -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:9103/health',timeout=2); exit(0 if r.status in (200,404) else 1)" >nul 2>&1
    if not errorlevel 1 goto tts_ok
)
echo     [WARN] TTS not ready
:tts_ok

echo     ASR model (9101) ...
for /L %%i in (1,1,45) do (
    timeout /t 2 /nobreak >nul
    "%PYTHON%" -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:9101/health',timeout=2); exit(0 if r.status in (200,404) else 1)" >nul 2>&1
    if not errorlevel 1 goto asr_ok
)
echo     [WARN] ASR not ready (model may still be loading)
:asr_ok

echo     GSVI engine (9105) ...
for /L %%i in (1,1,45) do (
    timeout /t 2 /nobreak >nul
    "%PYTHON%" -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:9105/ready',timeout=2); exit(0 if r.status in (200,404) else 1)" >nul 2>&1
    if not errorlevel 1 goto gsvi_ok
)
echo     [WARN] GSVI not ready (model may still be loading)
:gsvi_ok

echo.
echo     ============================================
echo       All services should be running
echo       ASR :9101   LLM :9102   TTS :9103
echo       Memory :9104   GSVI :9105   Bridge :9528
echo     ============================================
echo.
start http://127.0.0.1:9528

echo Press any key to stop all services...
pause >nul

echo.
echo Stopping...
"%PYTHON%" scripts\lifecycle.py stop >nul 2>&1
timeout /t 2 /nobreak >nul
echo Done.
