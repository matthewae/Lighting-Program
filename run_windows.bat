@echo off
cd /d "%~dp0"
set PY=python
if exist "C:\venv\minidesk\Scripts\python.exe" set PY=C:\venv\minidesk\Scripts\python.exe
"%PY%" -m minidesk %*
if errorlevel 1 pause
