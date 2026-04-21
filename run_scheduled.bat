@echo off
setlocal

call "%~dp0scripts\run_scheduled.bat"
exit /b %ERRORLEVEL%
