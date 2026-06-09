# Kindle Dashboard push agent — one-command install (run on the [monitored Windows machine]).
# Served by the dashboard at /agent/install.ps1; copy the full command with the address from the settings page and run it on Windows.
#
# Usage (the settings page gives the full command):
#   $u='http://<dashboard-IP>:<port>'; iwr "$u/agent/install.ps1" -UseBasicParsing -OutFile "$env:TEMP\kda.ps1"; `
#     powershell -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\kda.ps1" $u 30
#   Uninstall: ... -File "$env:TEMP\kda.ps1" uninstall
#
# Once installed: collects local metrics every <interval> seconds and pushes to the dashboard; a scheduled task auto-starts it at login; the machine appears automatically under the settings page "Device monitoring".
param(
    [string]$Url,
    [int]$Interval = 30,
    [string]$Id = $env:COMPUTERNAME
)
$ErrorActionPreference = "Stop"

$AgentDir = Join-Path $env:LOCALAPPDATA "kindle-dash-agent"
$TaskName = "KindleDashAgent"
$AgentPath = Join-Path $AgentDir "push_agent.ps1"

function Stop-AgentProcs {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*kindle-dash-agent*push_agent.ps1*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Uninstall-Agent {
    Write-Host "==> Uninstalling push agent..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Stop-AgentProcs
    if (Test-Path $AgentDir) { Remove-Item $AgentDir -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Host "OK Uninstalled: stopped reporting, removed login autostart (scheduled task), deleted $AgentDir."
}

if ($Url -eq "uninstall") { Uninstall-Agent; return }
if (-not $Url -or ($Url -notmatch '^https?://')) {
    Write-Host "X Usage: ... -File install.ps1 <dashboard address http://IP:port> [interval-seconds] [id]"; return
}
if ($Interval -lt 5) { $Interval = 30 }
$Url = $Url.TrimEnd('/')

Write-Host "==> Installing to $AgentDir (interval ${Interval}s, id $Id)..."
Stop-AgentProcs
New-Item -ItemType Directory -Force -Path $AgentDir | Out-Null
Invoke-WebRequest "$Url/agent/push_agent.ps1"     -UseBasicParsing -OutFile $AgentPath
Invoke-WebRequest "$Url/agent/collect_windows.ps1" -UseBasicParsing -OutFile (Join-Path $AgentDir "collect_windows.ps1")
@{ url = $Url; id = $Id; interval = $Interval } | ConvertTo-Json | Set-Content (Join-Path $AgentDir "agent.json") -Encoding UTF8

# Scheduled task: start the agent at login (hidden window, bypass execution policy)
$run = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$AgentPath`""
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $run
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "OK Login autostart set (scheduled task $TaskName)."
} catch {
    Write-Host "! Scheduled-task registration failed ($($_.Exception.Message)); the agent still starts now, but autostart-at-login wasn't set."
}

# Start one instance right now (hidden window)
Start-Process powershell -WindowStyle Hidden -ArgumentList $run

Write-Host "OK Push agent started, reporting every ${Interval} seconds."
Write-Host "   Back in the dashboard settings page 'Device monitoring' -> this machine (id $Id) appears automatically; you can rename it and pick metrics."
Write-Host "   Uninstall: replace the end of that command with uninstall and run it again."
