@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === EXNESS AI TRADER V4 - Installation ===
py -3.12 -m venv .venv 2>nul
if errorlevel 1 py -3.11 -m venv .venv 2>nul
if errorlevel 1 py -3 -m venv .venv
if errorlevel 1 (
  echo Python est introuvable. Installez Python 3.11 ou 3.12 64 bits avec "Add Python to PATH".
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo Echec de l'installation des dependances.
  pause
  exit /b 1
)
echo Installation terminee. Lancez BACKTEST.bat puis LANCER.bat.
pause
