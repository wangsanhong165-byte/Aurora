@echo off
setlocal
cd /d "%~dp0"
python scripts\lifecycle.py start --mode full
endlocal
