@echo off
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
call scripts\launch.cmd web
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
