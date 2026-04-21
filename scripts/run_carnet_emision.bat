@echo off
setlocal

set PROJECT_ROOT=%~dp0..
cd /d "%PROJECT_ROOT%"

if not exist "logs" mkdir "logs"
if not exist "data" mkdir "data"
if not exist "test" mkdir "test"
if not exist "__pycache__" mkdir "__pycache__"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
set RUN_LOG=logs\run_carnet_emision_%TS%.log

echo [INFO] Guardando consola en %RUN_LOG%
python -m app.carnet_emision >> "%RUN_LOG%" 2>&1
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] El flujo termino con codigo %EXIT_CODE%.
  echo [ERROR] Revisa: %RUN_LOG%
) else (
  echo.
  echo [OK] Flujo finalizado correctamente.
  echo [OK] Log de consola: %RUN_LOG%
)

exit /b %EXIT_CODE%
