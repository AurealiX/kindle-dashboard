<#
Kindle 一键卸载/还原(Windows 版):停看板、移除开机自启、删脚本与图片、恢复系统界面 —— 像没装过。
对应 macOS/Linux 的 installers/kindle/uninstall.sh,逻辑一致。Kindle 端命令一字不改。
用法(右键 PowerShell『以管理员身份运行』,配 USB 网卡需要):
  powershell -ExecutionPolicy Bypass -File installers\kindle\uninstall.ps1 [-KindleIp 192.168.15.244]
⚠ 尚未在真机(Windows + Kindle)上验证。
#>
param([string]$KindleIp = "192.168.15.244")
$ErrorActionPreference = "Stop"
function Fail($m){ Write-Host "X $m" -ForegroundColor Red; exit 1 }

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { Fail "没找到 ssh。请装 Windows 自带 OpenSSH 客户端(设置 -> 应用 -> 可选功能 -> OpenSSH 客户端)。" }
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)

# USB 网络:与 install.ps1 对称,自动把 Kindle USB 网卡配成 192.168.15.201/24
function Ensure-UsbRoute {
  if ($KindleIp -ne "192.168.15.244") { return $true }
  if (Test-Connection -Count 1 -Quiet $KindleIp -ErrorAction SilentlyContinue) { return $true }
  Write-Host "==> USB 网络未通,自动配置本机 USB 接口..."
  if (-not $IsAdmin) { Write-Host "   ! 配网卡需要管理员。请右键 PowerShell『以管理员身份运行』再跑。" -ForegroundColor Yellow; return $false }
  $cands = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -like '169.254.*' }
  foreach ($c in $cands) {
    $alias = $c.InterfaceAlias
    Write-Host "   检测到候选 USB 接口『$alias』,临时配 192.168.15.201..."
    try { netsh interface ipv4 set address name="$alias" static 192.168.15.201 255.255.255.0 | Out-Null } catch {}
    Start-Sleep -Seconds 2
    if (Test-Connection -Count 1 -Quiet $KindleIp -ErrorAction SilentlyContinue) { Write-Host "   √ USB 网络已通" -ForegroundColor Green; return $true }
  }
  return $false
}
if (-not (Ensure-UsbRoute)) { Write-Host "! USB 网络仍未通(排查同 install.ps1);若改用 WiFi:加参数 -KindleIp <KindleWiFiIP>" -ForegroundColor Yellow }

Write-Host "提示:接下来可能要求输入 Kindle 的 root 密码(越狱默认 mario)。"
Write-Host "==> 还原 Kindle($KindleIp)..."
$O = @("-o","StrictHostKeyChecking=no")
$remote = "[ -f /mnt/us/stop.sh ] && sh /mnt/us/stop.sh; " +
          "/usr/sbin/mntroot rw 2>/dev/null || true; " +
          "grep -v '/mnt/us/start.sh' /etc/crontab/root > /tmp/cr.tmp 2>/dev/null && mv /tmp/cr.tmp /etc/crontab/root; " +
          "/usr/sbin/mntroot ro 2>/dev/null || true; " +
          "rm -f /mnt/us/start.sh /mnt/us/stop.sh /mnt/us/dashboard.conf /mnt/us/frame.png /mnt/us/frame_new.png /mnt/us/dashboard.pid; " +
          "/sbin/initctl start framework 2>/dev/null || true; " +
          "/sbin/initctl start pmond 2>/dev/null || true; " +
          "echo cleaned"
& ssh @O "root@$KindleIp" $remote
if ($LASTEXITCODE -ne 0) { Fail "无法 SSH 到 Kindle。" }

Write-Host ""
Write-Host "√ 已还原:停看板、移除开机自启、删除脚本与图片、恢复界面。" -ForegroundColor Green
Write-Host "  建议重启 Kindle 彻底恢复(长按电源键约 40 秒)。"
