@echo off
setlocal EnableExtensions
REM s7py portable (Windows): virtuelle Umgebung anlegen und Abhaengigkeiten installieren.
cd /d "%~dp0"

REM --- Python finden: 3.13/3.12 bevorzugen (sichere fertige Pakete/Wheels) ---
REM Jeden Kandidaten wirklich starten (nicht nur "where").
set "PY="
py -3.13 --version >nul 2>&1 && set "PY=py -3.13"
if not defined PY py -3.12 --version >nul 2>&1 && set "PY=py -3.12"
if not defined PY py -3.11 --version >nul 2>&1 && set "PY=py -3.11"
if not defined PY py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY python3 --version >nul 2>&1 && set "PY=python3"

if not defined PY goto :no_python

echo Verwende Python-Aufruf: %PY%
for /f "tokens=*" %%v in ('%PY% --version 2^>^&1') do echo   Version: %%v

REM --- Mindestversion 3.11 pruefen ---
%PY% -c "import sys; sys.exit(0 if sys.version_info[:2]>=(3,11) else 1)"
if errorlevel 1 (
    echo Fehler: Python 3.11 oder neuer erforderlich.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Erstelle virtuelle Umgebung in .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Fehler beim Anlegen der virtuellen Umgebung.
        pause
        exit /b 1
    )
) else (
    echo Virtuelle Umgebung .venv existiert bereits.
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip

REM --only-binary=:all: : nur fertige Pakete verwenden, nichts kompilieren.
pip install --only-binary=:all: -r requirements.txt
if errorlevel 1 goto :pip_failed
pip install -e ".[dev]"
if errorlevel 1 goto :pip_failed

echo.
echo s7py ist eingerichtet.
echo   Starten:  run.bat
echo   Oder:     .venv\Scripts\activate  ^&^&  s7py
echo   Tests:    .venv\Scripts\activate  ^&^&  python -m pytest
echo.
echo Hinweis: python-snap7 3.0 ist reines Python — keine Snap7-DLL noetig.
echo Netzwerkzugriff auf die SPS (Port 102) muss auf dem Ziel-PC moeglich sein.
echo.
pause
exit /b 0

:pip_failed
echo.
echo Fehler bei pip install.
echo.
echo Wahrscheinliche Ursache: Fuer die installierte Python-Version gibt es noch
echo keine fertigen Pakete - sogenannte Wheels. Python 3.14 ist dafuer oft zu neu.
echo.
echo Empfehlung:
echo   1. Python 3.13 installieren: https://www.python.org/downloads/
echo      Im Installer "Add python.exe to PATH" aktivieren.
echo   2. Den Ordner .venv in diesem Verzeichnis loeschen.
echo   3. setup.bat erneut starten.
echo.
pause
exit /b 1

:no_python
echo Fehler: Python nicht gefunden oder nicht startbar.
echo.
echo Bitte Python 3.13 installieren:
echo   https://www.python.org/downloads/
echo Im Installer die Option "Add python.exe to PATH" aktivieren.
echo.
echo Hinweis: Falls Python aus dem Microsoft Store kommt, kann ein
echo Platzhalter das Starten verhindern. Deaktivieren unter:
echo   Einstellungen - Apps - Erweiterte App-Einstellungen -
echo   App-Ausfuehrungsaliase - python.exe / python3.exe ausschalten.
echo Danach dieses Fenster schliessen und setup.bat erneut starten.
echo.
pause
exit /b 1
