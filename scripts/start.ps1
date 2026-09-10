# Privacy Guardian - start backend + frontend (local only, from repo root)
$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) { Write-Error "No .venv. Run .\scripts\setup.ps1 first." }

Write-Host "Starting backend on http://127.0.0.1:8000 ..."
$backend = Start-Process -FilePath ".venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "app.backend.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WindowStyle Hidden -PassThru
Write-Host "Backend PID $($backend.Id)"

if (Test-Path "app\frontend\package.json") {
    Write-Host "Starting frontend dev server on http://127.0.0.1:5173 ..."
    Push-Location app\frontend
    $frontend = Start-Process -FilePath "npm" -ArgumentList "run", "dev" -WindowStyle Hidden -PassThru
    Pop-Location
    Write-Host "Frontend PID $($frontend.Id)"
}

Write-Host "Backend:  http://127.0.0.1:8000/docs   Frontend: http://127.0.0.1:5173"