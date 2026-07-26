@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "SOULLINK_NODE="
where node.exe >nul 2>&1 && set "SOULLINK_NODE=node.exe"
if not defined SOULLINK_NODE if exist "%ProgramFiles%\nodejs\node.exe" set "SOULLINK_NODE=%ProgramFiles%\nodejs\node.exe"
if not defined SOULLINK_NODE if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" set "SOULLINK_NODE=%LOCALAPPDATA%\Programs\nodejs\node.exe"

if not defined SOULLINK_NODE (
    echo [FAILED] Node.js was not found.
    echo Install Node.js or add node.exe to PATH.
    if "%~1"=="" pause
    exit /b 9009
)

"%SOULLINK_NODE%" scripts\soulctl.cjs %*
set "SOULLINK_EXIT=%ERRORLEVEL%"
if not "%SOULLINK_EXIT%"=="0" (
    echo.
    echo [FAILED] SoulLink exited with code %SOULLINK_EXIT%.
    echo Run: soulctl.cmd doctor
    if "%~1"=="" pause
)
exit /b %SOULLINK_EXIT%
