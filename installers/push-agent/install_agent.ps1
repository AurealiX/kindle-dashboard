# Kindle Dashboard 推送 agent —— 一键安装(在【被监控的 Windows 机】上运行)。
# 由看板服务在 /agent/install.ps1 提供;在设置页复制带地址的整行命令到 Windows 上运行即可。
#
# 用法(设置页会给出完整命令):
#   $u='http://<看板IP>:<端口>'; iwr "$u/agent/install.ps1" -UseBasicParsing -OutFile "$env:TEMP\kda.ps1"; `
#     powershell -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\kda.ps1" $u 30
#   卸载:... -File "$env:TEMP\kda.ps1" uninstall
#
# 装好后:每「间隔」秒采集本机指标推给看板;用『计划任务』设登录自启;本机会自动出现在看板设置页「设备监控」。
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
    Write-Host "==> 卸载推送 agent..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Stop-AgentProcs
    if (Test-Path $AgentDir) { Remove-Item $AgentDir -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Host "OK 已卸载:停止上报、清登录自启(计划任务)、删除 $AgentDir。"
}

if ($Url -eq "uninstall") { Uninstall-Agent; return }
if (-not $Url -or ($Url -notmatch '^https?://')) {
    Write-Host "X 用法: ... -File install.ps1 <看板地址 http://IP:端口> [间隔秒] [标识]"; return
}
if ($Interval -lt 5) { $Interval = 30 }
$Url = $Url.TrimEnd('/')

Write-Host "==> 安装到 $AgentDir(间隔 ${Interval}s,标识 $Id)..."
Stop-AgentProcs
New-Item -ItemType Directory -Force -Path $AgentDir | Out-Null
Invoke-WebRequest "$Url/agent/push_agent.ps1"     -UseBasicParsing -OutFile $AgentPath
Invoke-WebRequest "$Url/agent/collect_windows.ps1" -UseBasicParsing -OutFile (Join-Path $AgentDir "collect_windows.ps1")
@{ url = $Url; id = $Id; interval = $Interval } | ConvertTo-Json | Set-Content (Join-Path $AgentDir "agent.json") -Encoding UTF8

# 计划任务:登录时启动 agent(隐藏窗口、绕过执行策略)
$run = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$AgentPath`""
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $run
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "OK 已设登录自启(计划任务 $TaskName)。"
} catch {
    Write-Host "! 计划任务注册失败($($_.Exception.Message));agent 仍会被立即启动,但开机自启没设上。"
}

# 立即启动一份(隐藏窗口)
Start-Process powershell -WindowStyle Hidden -ArgumentList $run

Write-Host "OK 推送 agent 已启动,每 ${Interval} 秒上报一次。"
Write-Host "   回看板设置页「设备监控」-> 本机(标识 $Id)会自动出现,可改名、选指标。"
Write-Host "   卸载:把那行命令末尾换成 uninstall 再跑一次。"
