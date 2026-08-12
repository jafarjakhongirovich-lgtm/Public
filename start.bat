@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Jarvis is not installed yet. Run install.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m jarvis
pause
