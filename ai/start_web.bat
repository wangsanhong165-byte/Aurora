@echo off
setlocal
cd /d "%~dp0"
python scripts\launcher.py web --pause-on-error
endlocal
