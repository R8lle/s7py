@echo off
setlocal EnableExtensions
REM Erzeugt ein ZIP-Archiv zum Kopieren auf einen anderen Windows-PC (ohne .venv).
cd /d "%~dp0"

set "STAMP="
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "STAMP=%%i"
if not defined STAMP set "STAMP=portable"
set "OUT_DIR=%~dp0dist"
set "ARCHIVE=%OUT_DIR%\s7py-portable-win-%STAMP%.zip"

if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = '%CD%';" ^
  "$dest = '%ARCHIVE%';" ^
  "$names = @('s7py.py','s7py','requirements.txt','requirements-build.txt','s7py_db.json.example','.gitignore','LICENSE','LICENSE_THIRD_PARTY.txt','s7py.spec','setup.bat','run.bat','setup.sh','run.sh','package-portable.bat','package-portable.sh','build-windows.bat');" ^
  "$paths = foreach ($n in $names) { Join-Path $root $n } | Where-Object { Test-Path $_ };" ^
  "if (Test-Path $dest) { Remove-Item $dest -Force };" ^
  "Compress-Archive -Path $paths -DestinationPath $dest -Force"

if errorlevel 1 (
    echo Fehler beim Erstellen des ZIP-Archivs.
    pause
    exit /b 1
)

echo.
echo Portable Paket erstellt:
echo   %ARCHIVE%
echo.
echo Auf dem Ziel-PC:
echo   1. Archiv entpacken
echo   2. setup.bat ausfuehren
echo   3. run.bat ausfuehren
echo.
pause
