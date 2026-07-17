# Windows PowerShell startup script for the Rental Intelligence Platform's
# web dashboard. See docs/35_Installation_and_Operations.md "Startup".
#
# Usage (from the project root, with .venv already created):
#   .\scripts\start_web.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at $VenvPython. Run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

Write-Host "Running health check..."
& $VenvPython scripts\health_check.py
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Health check reported at least one failure — see above. Continuing anyway."
}

Write-Host "Starting the web dashboard at http://127.0.0.1:5000/ ..."
& $VenvPython -m flask --app "src.web.application:create_app" run
