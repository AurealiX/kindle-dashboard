# Kindle Dashboard push agent (Windows) — runs on the [monitored Windows machine].
# Loop: collect local metrics -> POST to the dashboard /api/device-metrics -> sleep for the interval.
# Config is read from agent.json in the same dir (written by install_agent.ps1). Normally no manual tuning needed; the scheduled task installs it and auto-starts at login.
$ErrorActionPreference = "SilentlyContinue"

$Dir = $PSScriptRoot
if (-not $Dir) { $Dir = Split-Path -Parent $MyInvocation.MyCommand.Path }
$cfg = Get-Content (Join-Path $Dir "agent.json") -Raw | ConvertFrom-Json
$Url = ([string]$cfg.url).TrimEnd('/')
$Id  = [string]$cfg.id
if (-not $Id) { $Id = $env:COMPUTERNAME }
$Interval = [int]$cfg.interval
if ($Interval -lt 5) { $Interval = 30 }
$HostName = $env:COMPUTERNAME
$Collector = Join-Path $Dir "collect_windows.ps1"

# JSON string escaping (so a " or \ in the ID/hostname doesn't break the body)
function Esc([string]$s) { return $s.Replace('\', '\\').Replace('"', '\"') }

while ($true) {
    $m = (& $Collector | Out-String).Trim()
    if ($m -and $m.StartsWith("{")) {
        $body = '{"id":"' + (Esc $Id) + '","hostname":"' + (Esc $HostName) + '","metrics":' + $m + '}'
        try {
            Invoke-RestMethod -Uri "$Url/api/device-metrics" -Method Post `
                -Body $body -ContentType "application/json" -TimeoutSec 10 | Out-Null
        } catch {}
    }
    Start-Sleep -Seconds $Interval
}
