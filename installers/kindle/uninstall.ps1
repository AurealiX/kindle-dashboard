<#
Kindle 一键卸载/还原(Windows 版):停看板、移除开机自启、删脚本与图片、恢复系统界面 —— 像没装过。
对应 macOS/Linux 的 installers/kindle/uninstall.sh,逻辑一致。Kindle 端命令一字不改。
用法(右键 PowerShell『以管理员身份运行』,配 USB 网卡需要):
  powershell -ExecutionPolicy Bypass -File installers\kindle\uninstall.ps1 [-KindleIp 192.168.15.244]
⚠ 尚未在真机(Windows + Kindle)上验证。
#>
param([string]$KindleIp = "192.168.15.244")
$ErrorActionPreference = "Stop"
# 临时配过静态 IP 的 USB 网卡,跑完(成功或失败)还原成自动获取(Windows netsh 是持久的,必须显式还原)。
$script:UsbAdapter = $null
function Restore-UsbRoute {
  if ($script:UsbAdapter) {
    try { netsh interface ipv4 set address name="$script:UsbAdapter" dhcp | Out-Null } catch {}
    Write-Host "  (已把临时配置的 USB 网卡『$script:UsbAdapter』还原成自动获取 IP)"
    $script:UsbAdapter = $null
  }
}
function Fail($m){ Restore-UsbRoute; Write-Host "X $m" -ForegroundColor Red; exit 1 }

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { Fail "没找到 ssh。请装 Windows 自带 OpenSSH 客户端(设置 -> 应用 -> 可选功能 -> OpenSSH 客户端)。" }
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)

# USB 网络:与 install.ps1 对称,自动把 Kindle USB 网卡配成 192.168.15.201/24
function Ensure-UsbRoute {
  if ($KindleIp -ne "192.168.15.244") { return $true }
  if (Test-Connection -Count 1 -Quiet $KindleIp -ErrorAction SilentlyContinue) { return $true }
  Write-Host "==> USB 网络未通,自动配置本机 USB 接口..."
  if (-not $IsAdmin) { Write-Host "   ! 配网卡需要管理员。请右键 PowerShell『以管理员身份运行』再跑。" -ForegroundColor Yellow; return $false }
  # 只配【已连接(Up)】的 169.254 网卡(那才是 Kindle USB),不碰断开的 WLAN/蓝牙/虚拟网卡。
  $upNames = @((Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' }).Name)
  $cands = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress -like '169.254.*' -and $upNames -contains $_.InterfaceAlias }
  if (-not $cands) {
    Write-Host "   ! 没找到【已连接】的 Kindle USB 网卡。多半 Kindle 还在【USB 存储盘模式】(显示成磁盘),不是网络模式。" -ForegroundColor Yellow
    Write-Host "     → 在 Kindle 上用 KUAL 启动 USBNetwork,再重跑;Windows 认成未知设备时到设备管理器装『远程 NDIS 兼容设备』。"
    return $false
  }
  foreach ($c in $cands) {
    $alias = $c.InterfaceAlias
    Write-Host "   检测到已连接的候选 USB 网卡『$alias』,临时配 192.168.15.201(跑完会还原)..."
    try { netsh interface ipv4 set address name="$alias" static 192.168.15.201 255.255.255.0 | Out-Null } catch {}
    $script:UsbAdapter = $alias
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

Restore-UsbRoute   # 还原临时配过的 USB 网卡为自动获取 IP

Write-Host ""
Write-Host "√ 已还原:停看板、移除开机自启、删除脚本与图片、恢复界面。" -ForegroundColor Green
Write-Host "  建议重启 Kindle 彻底恢复(长按电源键约 40 秒)。"
