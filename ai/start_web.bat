@echo off
cd /d "%~dp0"
echo Starting Monika Web UI...
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe run.py --text --ui web
pause

