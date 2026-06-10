<#
Kindle Dashboard — Windows server uninstall. Mirrors installers/macos/uninstall.sh.
Stops the service, removes the scheduled task and firewall rule. Config and data are kept
unless you pass -Purge (then the external config dir and repo data\ are deleted too).

Usage (admin PowerShell, needed to remove the firewall rule):
  powershell -ExecutionPolicy Bypass -File installers\windows\uninstall.ps1 [-Purge]
#>
param([switch]$Purge)
$ErrorActionPreference = "SilentlyContinue"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$TaskName = "KindleDashboard"

Write-Host "==> Stopping service + removing autostart..."
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*server.run*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# leftover render chrome (kdash-render marker)
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*kdash-render*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "==> Removing firewall rule..."
Remove-NetFirewallRule -DisplayName "Kindle Dashboard"

if ($Purge) {
    Write-Host "==> Purging config + data..."
    Remove-Item (Join-Path $env:USERPROFILE ".config\kindle-dashboard") -Recurse -Force
    Remove-Item (Join-Path $Repo "data") -Recurse -Force
    Remove-Item (Join-Path $Repo ".venv") -Recurse -Force
}

Write-Host "OK Uninstalled.$(if (-not $Purge) { ' Config kept at ' + (Join-Path $env:USERPROFILE '.config\kindle-dashboard') + ' (use -Purge for a full wipe).' })" -ForegroundColor Green
