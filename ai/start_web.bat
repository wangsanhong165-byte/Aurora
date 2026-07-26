@echo off
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
python scripts\launcher.py web 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [FAILED] Web launcher exited with code %EXIT_CODE%.
    echo Run this command for diagnostics:
    echo python scripts\launcher.py doctor
    echo.
    pause
)
endlocal
exit /b %EXIT_CODE%
