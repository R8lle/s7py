@echo off
setlocal EnableExtensions
REM Baut das Windows-Setup (Inno Setup). Doppelklick reicht auf einem Windows-PC.
REM Ergebnis: dist\installer\s7py-<version>-setup.exe
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\windows\build.ps1"
if errorlevel 1 (
    echo.
    echo Build fehlgeschlagen.
    pause
    exit /b 1
)

echo.
pause
