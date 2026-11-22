@echo off
rem Brings the app to its newest version. Your searches and settings (the folder "data") are kept.
cd /d "%~dp0"
python --version >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" in the installer. Then run this file again.
  pause
  exit /b 1
)
rem One block: it is read whole before it runs, so this file may itself be replaced by the update.
(
  python update.py %*
  pause
  exit /b
)
