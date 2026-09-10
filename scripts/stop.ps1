# Privacy Guardian - stop backend/frontend
Get-Process -Name "uvicorn","node" -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*E:\Web App\Cleaner*" -or $_.CommandLine -like "*app.backend.main*"
} | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "Stopped Privacy Guardian processes (if any)."