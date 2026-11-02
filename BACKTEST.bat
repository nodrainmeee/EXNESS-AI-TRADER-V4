@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Lancez d'abord INSTALLER.bat.
  pause
  exit /b 1
)
echo MT5 doit etre ouvert (compte demo). Test historique EURUSD et XAUUSD, 30000 bougies M15.
".venv\Scripts\python.exe" src\backtest.py --symbol EURUSD --tf M15 --bars 30000 --optimize
".venv\Scripts\python.exe" src\backtest.py --symbol XAUUSD --tf M15 --bars 30000 --optimize
pause
