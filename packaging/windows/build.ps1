# Baut den Windows-Installer lokal (gleiche Schritte wie
# .github/workflows/package-windows.yml). Benoetigt Internet, Python 3.11+
# und Inno Setup 6.
#
#   Im Projektordner (PowerShell):
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
#
# Ergebnis: dist\installer\s7py-<version>-setup.exe und selftest.txt
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..\..")
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Step([string]$text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Run {
    & $args[0] @($args | Select-Object -Skip 1)
    if ($LASTEXITCODE -ne 0) { throw "Fehlgeschlagen ($LASTEXITCODE): $($args -join ' ')" }
}

Step "Python"
$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $py = (& py -3 -c "import sys; print(sys.executable)") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = (& python -c "import sys; print(sys.executable)") }
if (-not $py) { throw "Python fehlt: https://www.python.org/downloads/windows/ (Haken bei 'Add python.exe to PATH')." }
Write-Host $py
if (-not (Test-Path .venv-build\Scripts\python.exe)) { Run $py -m venv .venv-build }
$vpy = (Resolve-Path .venv-build\Scripts\python.exe).Path
Run $vpy -m pip install --upgrade pip --quiet
Run $vpy -m pip install -e ".[dev,opcua]" pyinstaller pillow --quiet

Step "Build-Kennung und Symbol"
New-Item -ItemType Directory -Force packaging\build | Out-Null
Run $vpy -m s7py.about --stamp
Get-Content s7py\_build.py
Run $vpy packaging\windows\make_icon.py

Step "PyInstaller"
Run $vpy -m PyInstaller packaging\windows\s7py.spec --distpath dist --workpath packaging\build\work --noconfirm

Step "Selbsttest (hoechstens 2 Minuten)"
$report = Join-Path (Get-Location) "selftest.txt"
$p = Start-Process -FilePath dist\s7py\s7py.exe -ArgumentList "--selftest", "`"$report`"" -PassThru
$done = $p.WaitForExit(120000)
if (-not $done) { Stop-Process -Id $p.Id -Force; Write-Host "ABGEBROCHEN nach 2 Minuten" -ForegroundColor Red }
if (Test-Path $report) { Get-Content $report } else { Write-Host "keine selftest.txt" }
if (-not $done -or $p.ExitCode -ne 0) { throw "Selbsttest fehlgeschlagen - bitte selftest.txt schicken." }

Step "Installer (Inno Setup)"
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install innosetup -y --no-progress
        $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
            Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $iscc) { throw "Inno Setup 6 fehlt: https://jrsoftware.org/isdl.php" }
}
$version = (& $vpy -c "import s7py; print(s7py.__version__)")
Run $iscc "/DAppVersion=$version" packaging\windows\installer.iss

Step "Fertig"
Get-ChildItem dist\installer\*.exe | ForEach-Object { Write-Host $_.FullName -ForegroundColor Green }
