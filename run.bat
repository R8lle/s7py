@echo off
setlocal EnableExtensions
REM s7py portable (Windows): Anwendung starten (nach setup.bat).
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Virtuelle Umgebung fehlt. Bitte zuerst ausfuehren:
    echo   setup.bat
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
s7py %*
