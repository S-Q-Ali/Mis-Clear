# Privacy Guardian - dev scripts
# Run from repo root.

$ErrorActionPreference = "Stop"

Write-Host "[1/4] Creating Python venv (uv) if missing..."
if (-not (Test-Path ".venv")) { uv venv --python 3.11 .venv }

Write-Host "[2/4] Synchronizing dependencies..."
uv sync

Write-Host "[3/4] Installing frontend dependencies..."
if (-not (Test-Path "app\frontend\node_modules")) {
    Push-Location app\frontend
    npm install
    Pop-Location
}

Write-Host "[4/4] Verifying backend tests..."
uv run pytest

Write-Host "Setup complete. Run .\scripts\start.ps1 to start."