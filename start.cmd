@echo off
rem Starts the app on this computer only and opens it in Chrome. Close this window to stop it.
cd /d "%~dp0"
python --version >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" in the installer. Then run this file again.
  pause
  exit /b 1
)
rem One block: it is read whole before it runs, so an update may replace this file while the app is running.
(
  python app.py serve --open
  if errorlevel 1 pause
  exit /b
)
