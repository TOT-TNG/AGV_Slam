@echo off
REM install.bat - Chay tu cmd.exe, goi install.ps1 (PowerShell) thuc hien cai dat.
REM   deploy\install.bat
REM   deploy\install.bat --no-seed

setlocal
set SCRIPT_DIR=%~dp0

if "%1"=="--no-seed" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1" -NoSeed
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1"
)
endlocal
