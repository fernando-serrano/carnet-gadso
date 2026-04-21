@echo off
setlocal

call "%~dp0scripts\run_carnet_emision.bat"
exit /b %ERRORLEVEL%
