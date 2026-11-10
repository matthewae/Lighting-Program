@echo off
cd /d "%~dp0"
python -m minidesk %*
if errorlevel 1 pause
