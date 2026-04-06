@echo off
setlocal

cd /d "%~dp0"

if not exist "logs" mkdir "logs"
if not exist "data" mkdir "data"
if not exist "test" mkdir "test"
if not exist "__pycache__" mkdir "__pycache__"

python carnet_emision.py
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] El flujo termino con codigo %EXIT_CODE%.
) else (
  echo.
  echo [OK] Flujo finalizado correctamente.
)

pause
exit /b %EXIT_CODE%
