@echo off
setlocal EnableExtensions
REM Baut eine startbare Windows-Anwendung (Ordner dist\s7py\ mit s7py.exe).
REM Nur unter Windows ausfuehren.
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Virtuelle Umgebung fehlt. Fuehre zuerst setup.bat aus ...
    call "%~dp0setup.bat"
)

if not exist ".venv\Scripts\activate.bat" (
    echo Abbruch: Einrichtung fehlgeschlagen - siehe Meldungen von setup.bat oben.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install pyinstaller
if errorlevel 1 (
    echo Fehler bei pip install pyinstaller.
    pause
    exit /b 1
)

pyinstaller --noconfirm --clean s7py.spec
if errorlevel 1 (
    echo Fehler beim Build.
    pause
    exit /b 1
)

echo.
echo Build fertig:
echo   dist\s7py\s7py.exe
echo.
echo Den gesamten Ordner dist\s7py\ auf den Ziel-PC kopieren.
echo Dort s7py.exe doppelklicken.
echo.
pause
