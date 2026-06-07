# Kindle Dashboard 推送 agent(Windows)—— 在【被监控的 Windows 机】上跑。
# 循环:采集本机指标 → POST 到看板 /api/device-metrics → sleep 间隔。
# 配置从同目录 agent.json 读(由 install_agent.ps1 写好)。一般不用手调,计划任务会装好并开机自启。
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

# JSON 字符串转义(防 ID/主机名里的 " 或 \ 破坏 body)
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
