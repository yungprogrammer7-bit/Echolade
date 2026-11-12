@echo off
setlocal
cd /d "%~dp0"
echo.
echo  Echolade - one-time setup (internet needed once for the speech model)
echo.
set PYCMD=
py -3.12 --version >nul 2>nul && set PYCMD=py -3.12
if "%PYCMD%"=="" py -3.11 --version >nul 2>nul && set PYCMD=py -3.11
if "%PYCMD%"=="" (
  echo Python 3.11 or 3.12 ^(64-bit^) was not found.
  echo Install it from https://www.python.org/downloads/windows/ and tick "Add Python to PATH", then run setup.bat again.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  %PYCMD% -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Downloading and verifying the speech model...
".venv\Scripts\python.exe" scripts\download_models.py
if errorlevel 1 goto failed
echo.
echo Setup complete. Double-click start.bat to open Echolade.
pause
exit /b 0
:failed
echo.
echo Setup did not finish. Read the message above, then run setup.bat again. It resumes where it stopped.
pause
exit /b 1
