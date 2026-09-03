# Build a shareable Windows folder: packaging/dist/DT_Analyser.zip
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Building frontend..."
Push-Location "$Root\frontend"
if (-not (Test-Path "node_modules")) { npm ci }
npm run build
Pop-Location

Write-Host "Installing Python build deps..."
Push-Location "$Root\backend"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
& .\.venv\Scripts\python.exe -m pip install -q pyinstaller
Pop-Location

Write-Host "Running PyInstaller..."
& "$Root\backend\.venv\Scripts\pyinstaller.exe" --noconfirm --distpath "$Root\packaging\dist" --workpath "$Root\packaging\build" "$Root\packaging\dt_analyser.spec"
Copy-Item "$Root\packaging\START_HERE.txt" "$Root\packaging\dist\DT_Analyser\START_HERE.txt" -Force

$Zip = "$Root\packaging\dist\DT_Analyser.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path "$Root\packaging\dist\DT_Analyser\*" -DestinationPath $Zip
Write-Host "Done: $Zip"
Write-Host "Send that zip. She extracts it and double-clicks DT_Analyser.exe"
