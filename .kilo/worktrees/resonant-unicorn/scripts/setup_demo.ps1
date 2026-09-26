# Windows convenience wrapper: create the venv, install, and set up the demo.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "==> Creating virtual environment" -ForegroundColor Cyan
Push-Location "$root\backend"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
Pop-Location

Write-Host "==> Building the demo corpus" -ForegroundColor Cyan
& "$root\backend\.venv\Scripts\python.exe" "$root\scripts\setup_demo.py" --reset

Write-Host "==> Installing frontend dependencies" -ForegroundColor Cyan
Push-Location "$root\frontend"
npm install
Pop-Location

Write-Host ""
Write-Host "Done. Start the two servers in separate terminals:" -ForegroundColor Green
Write-Host "  cd backend; .venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000"
Write-Host "  cd frontend; npm run dev"
