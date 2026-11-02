@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Lancez d'abord INSTALLER.bat.
  pause
  exit /b 1
)
echo MT5 doit etre ouvert (compte demo). Recherche de strategie : 3 strategies x 4 timeframes. Patience...
".venv\Scripts\python.exe" src\research.py
pause
