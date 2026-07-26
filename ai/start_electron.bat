@echo off
setlocal
cd /d "%~dp0"
python scripts\launcher.py electron --pause-on-error
endlocal
