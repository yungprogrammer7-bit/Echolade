@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Echolade is not set up yet. Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m backend %*
pause
