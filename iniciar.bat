@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primeira execucao: instalando dependencias...
  python setup.py || (echo Falha no setup. & pause & exit /b 1)
)
if not exist "node_modules" (
  call npm install --no-audit --no-fund
  call npm --prefix frontend install --no-audit --no-fund
)
echo.
echo Abrindo http://localhost:5173  (API na porta 8010)
if not defined NO_BROWSER start "" http://localhost:5173
call npm run dev
