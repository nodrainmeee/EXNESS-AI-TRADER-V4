@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Lancez d'abord INSTALLER.bat.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" src\app.py
if errorlevel 1 pause
