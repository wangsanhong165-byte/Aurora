@echo off
setlocal
cd /d "%~dp0.."

set "BOOTSTRAP_PYTHON="
if defined MAIN_PYTHON if exist "%MAIN_PYTHON%" set "BOOTSTRAP_PYTHON=%MAIN_PYTHON%"
if not defined BOOTSTRAP_PYTHON if exist "C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe" set "BOOTSTRAP_PYTHON=C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe"

if defined BOOTSTRAP_PYTHON (
    "%BOOTSTRAP_PYTHON%" scripts\launcher.py %*
    exit /b %ERRORLEVEL%
)

where python.exe >nul 2>&1
if not errorlevel 1 (
    python.exe scripts\launcher.py %*
    exit /b %ERRORLEVEL%
)

where py.exe >nul 2>&1
if not errorlevel 1 (
    py.exe -3 scripts\launcher.py %*
    exit /b %ERRORLEVEL%
)

echo [FAILED] No Python interpreter was found.
echo Expected: C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe
exit /b 9009
