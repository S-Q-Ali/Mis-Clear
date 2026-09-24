# Privacy Guardian - stop backend/frontend (local only)
# Matches processes by command line / executable path, so it also stops the
# backend that start.ps1 launches as `python.exe -m uvicorn ...` (whose process
# name is "python", not "uvicorn").
$ErrorActionPreference = "SilentlyContinue"

$repo = Split-Path -Parent $PSScriptRoot

$targets = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='node.exe' OR Name='uvicorn.exe'" |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -like "*app.backend.main*" -or
            $_.CommandLine -like "*$repo*" -or
            $_.ExecutablePath -like "$repo*"
        )
    }

if (-not $targets) {
    Write-Host "No Privacy Guardian processes found."
    return
}

foreach ($proc in $targets) {
    Write-Host "Stopping $($proc.Name) PID $($proc.ProcessId)..."
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "Stopped Privacy Guardian processes."
