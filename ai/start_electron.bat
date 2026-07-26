@echo off
setlocal
cd /d "%~dp0frontend"
npm.cmd run electron:start
endlocal
