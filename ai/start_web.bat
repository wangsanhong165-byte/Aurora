@echo off
cd /d "%~dp0"

:: Kill any existing bridge on port 9528
for /f "tokens=5" %%a in ('netstat -ano ^| find ":9528" ^| find "LISTENING"') do (
    echo Killing old bridge process PID=%%a
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo Starting Monika Live2D...
echo.
echo This will start:
echo   - ASR service (:8000)
echo   - LLM service (:8020)
echo   - TTS service (:8030)
echo   - Memory service (:8040)
echo   - GSVI v2Pro (:8050)
echo   - Live2D Bridge (:9528)
echo.
echo Open http://127.0.0.1:9528 in your browser
echo Close this window to stop all services.
echo.

C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe scripts\start_bridge.py
pause