@echo off
rem Starts the app so that people you invited can open it from their own devices on the home network.
rem Nobody gets in without a link you made in the app (the share button).
rem Windows may ask once to let Python through the firewall: allow it for private networks only.
rem The app speaks plain HTTP and has no passwords: home network only, never open it to the internet.
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
  python app.py serve --lan --open
  if errorlevel 1 pause
  exit /b
)
