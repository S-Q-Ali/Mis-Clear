# Privacy Guardian - creates a "Privacy Guardian" shortcut on the Desktop
# that launches start.cmd (double-click one-click runner).
# Re-run to refresh/overwrite. Usage:  powershell -ExecutionPolicy Bypass -File .\create-shortcut.ps1
param(
    [string]$ShortcutName = "Privacy Guardian",
    [string]$DesktopDir = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $repoRoot "start.cmd"
if (-not (Test-Path -LiteralPath $target)) {
    throw "start.cmd not found at $target"
}

if (-not $DesktopDir) {
    $DesktopDir = [Environment]::GetFolderPath("Desktop")
}
if (-not $DesktopDir -or -not (Test-Path -LiteralPath $DesktopDir)) {
    $DesktopDir = [Environment]::GetFolderPath("CommonDesktopDirectory")
}
if (-not $DesktopDir -or -not (Test-Path -LiteralPath $DesktopDir)) {
    throw "Could not determine the Desktop directory."
}

$shortcutPath = Join-Path $DesktopDir "$ShortcutName.lnk"
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($shortcutPath)
$lnk.TargetPath = $target
$lnk.WorkingDirectory = $repoRoot
$lnk.Description = "Start Privacy Guardian (backend + frontend + Colab tunnel)"
$lnk.Save()

Write-Host "Created: $shortcutPath"
Write-Host "Target : $target"
Write-Host "Workdir: $repoRoot"