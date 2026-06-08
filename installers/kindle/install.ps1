<#
Kindle 一键配置(Windows 版):推送 start/stop、写服务地址、装开机自启、启动显示。
对应 macOS/Linux 的 installers/kindle/install.sh,**逻辑一致**;仅平台命令不同
(本机 IP 探测 / 用 netsh 配 USB 网卡 / 用 Windows 自带 ssh+scp)。推到 Kindle 上的脚本与 Kindle 端逻辑一字不改。

前提:Kindle 已越狱 + 已开 USBNetwork(SSH);Windows 10+ 自带 OpenSSH 客户端;配 USB 网卡需管理员。
用法(右键 PowerShell『以管理员身份运行』):
  powershell -ExecutionPolicy Bypass -File installers\kindle\install.ps1
  可选参数:-KindleIp 192.168.15.244  -ServerUrl http://<电脑IP>:8585  -Interval 20
⚠ 本脚本尚未在真机(Windows + Kindle)上验证,首次使用请按提示排查。
#>
param(
  [string]$KindleIp  = "192.168.15.244",
  [string]$ServerUrl = "",
  [int]$Interval     = 0
)
$ErrorActionPreference = "Stop"
$KDIR = $PSScriptRoot
function Fail($m){ Write-Host "X $m" -ForegroundColor Red; exit 1 }

# 0. 前置:ssh/scp 存在 + 是否管理员
if (-not (Get-Command ssh  -ErrorAction SilentlyContinue)) { Fail "没找到 ssh。请装 Windows 自带 OpenSSH 客户端:设置 -> 应用 -> 可选功能 -> 添加『OpenSSH 客户端』,再重跑。" }
if (-not (Get-Command scp  -ErrorAction SilentlyContinue)) { Fail "没找到 scp(同上,装 OpenSSH 客户端)。" }
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)

# 1. 自动探测服务地址(本机局域网 IP,家用网段优先;开代理时也不会误选 198.18 之类)
if (-not $ServerUrl) {
  $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
        Sort-Object @{Expression={ switch -Wildcard ($_.IPAddress) { '192.168.*'{0} '10.*'{1} '172.*'{2} default{9} } }} |
        Select-Object -First 1 -ExpandProperty IPAddress
  if (-not $ip) { $ip = "127.0.0.1" }
  $ServerUrl = "http://${ip}:8585"
}
Write-Host "Kindle: $KindleIp    服务地址: $ServerUrl"

# 2. Kindle 拉图刷新间隔(秒):参数优先,否则交互询问,默认 20(<5 视为无效)
if ($Interval -lt 5) {
  $ans = Read-Host "==> Kindle 多久拉一次新图?越短越实时、越费电。常用 10/20/30/60,回车默认 20"
  if ($ans -match '^[0-9]+$' -and [int]$ans -ge 5) { $Interval = [int]$ans } else { $Interval = 20 }
}
Write-Host "   刷新间隔:${Interval}s"

# Windows 默认不广播 mDNS(没装 Bonjour),不写 .local 兜底;靠固定 IP 更稳(见 docs/install.md)
$ServerUrlAlt = ""

# 3. USB 网络:把 Kindle 的 USB 网卡配成 192.168.15.201/24(与 .sh 的 ensure_usb_route 对称)
function Ensure-UsbRoute {
  if ($KindleIp -ne "192.168.15.244") { return $true }                 # 仅 USBNetwork 标准地址才需要
  if (Test-Connection -Count 1 -Quiet $KindleIp -ErrorAction SilentlyContinue) { return $true }  # 已通则跳过(幂等)
  Write-Host "==> USB 网络未通,自动配置本机 USB 接口..."
  if (-not $IsAdmin) { Write-Host "   ! 配网卡需要管理员。请右键 PowerShell『以管理员身份运行』再跑本脚本。" -ForegroundColor Yellow; return $false }
  # 拿到 169.254(APIPA,没 DHCP)的网卡,基本就是 Kindle 的 USB 网卡
  $cands = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -like '169.254.*' }
  foreach ($c in $cands) {
    $alias = $c.InterfaceAlias
    Write-Host "   检测到候选 USB 接口『$alias』,临时配 192.168.15.201(只动这块 Kindle 网卡,不影响你上网)..."
    try { netsh interface ipv4 set address name="$alias" static 192.168.15.201 255.255.255.0 | Out-Null } catch {}
    Start-Sleep -Seconds 2
    if (Test-Connection -Count 1 -Quiet $KindleIp -ErrorAction SilentlyContinue) { Write-Host "   √ USB 网络已通" -ForegroundColor Green; return $true }
  }
  return $false
}
if (-not (Ensure-UsbRoute)) {
  Write-Host "! USB 网络仍未通。排查:① 设备管理器里 Kindle 是否被识别为『网络适配器/USB RNDIS』(没有就要装 RNDIS 驱动)② 用支持数据传输的线 ③ Kindle 已开 USBNetwork。若改用 WiFi:加参数 -KindleIp <KindleWiFiIP> -ServerUrl http://<电脑IP>:8585" -ForegroundColor Yellow
}

# 4. SSH 推送 + 安装。Windows OpenSSH 不支持 ControlMaster 连接复用,所以**会让你输几次密码**(越狱默认 mario)
$O = @("-o","StrictHostKeyChecking=no")
Write-Host "提示:接下来会要求输入 Kindle 的 root 密码(越狱默认 mario;改过用你的)。会输几次,正常。"
& ssh @O "root@$KindleIp" "echo connected"
if ($LASTEXITCODE -ne 0) { Fail "无法 SSH 到 Kindle。确认 USB 网络通、Kindle 开了 USBNetwork。" }

Write-Host "==> 备份旧版(若有)..."
& ssh @O "root@$KindleIp" "if [ -f /mnt/us/start.sh ] || [ -f /mnt/us/stop.sh ]; then mkdir -p /mnt/us/kindle-dash-backup; cp /mnt/us/start.sh /mnt/us/kindle-dash-backup/ 2>/dev/null; cp /mnt/us/stop.sh /mnt/us/kindle-dash-backup/ 2>/dev/null; cp /etc/crontab/root /mnt/us/kindle-dash-backup/crontab.root 2>/dev/null; echo '  backup ok'; else echo '  (无旧版,跳过)'; fi"

Write-Host "==> 推送脚本..."
& scp @O (Join-Path $KDIR "start.sh") (Join-Path $KDIR "stop.sh") "root@${KindleIp}:/mnt/us/"
if ($LASTEXITCODE -ne 0) { Fail "scp 推送 start.sh/stop.sh 失败。" }

Write-Host "==> 写配置、装自启、启动..."
# 单行 sh 命令(分号串联),避免 Windows 传多行参数的引号坑;在 Kindle busybox sh 上执行
$remote = "echo 'SERVER_URL=$ServerUrl' > /mnt/us/dashboard.conf; " +
          "echo 'SERVER_URL_ALT=$ServerUrlAlt' >> /mnt/us/dashboard.conf; " +
          "echo 'INTERVAL=$Interval' >> /mnt/us/dashboard.conf; " +
          "chmod +x /mnt/us/start.sh /mnt/us/stop.sh; " +
          "/usr/sbin/mntroot rw 2>/dev/null || true; " +
          "grep -v '/mnt/us/start.sh' /etc/crontab/root > /tmp/cr.tmp 2>/dev/null && mv /tmp/cr.tmp /etc/crontab/root; " +
          "echo '@reboot sleep 30 && /mnt/us/start.sh # kindle-dashboard' >> /etc/crontab/root; " +
          "/usr/sbin/mntroot ro 2>/dev/null || true; " +
          "command -v fbink >/dev/null 2>&1 || echo 'WARN: 未找到 fbink,刷屏会失败 —— 请通过 KUAL/越狱工具安装 fbink 后重跑'; " +
          "setsid /mnt/us/start.sh < /dev/null > /mnt/us/dashboard.log 2>&1 &" +
          " echo started"
& ssh @O "root@$KindleIp" $remote

Write-Host ""
Write-Host "√ 完成。Kindle 应开始显示看板(横放摆,顶边朝右)。" -ForegroundColor Green
Write-Host "  之后改配置在网页保存即可,Kindle 侧不用再碰。"
Write-Host ""
Write-Host "! 重要:Kindle 按固定地址 $ServerUrl 拉图——【看板服务所在那台机器】的 IP 一旦变,看板就停更。请把它固定:" -ForegroundColor Yellow
Write-Host "  - 服务在 NAS / 常开主机:去路由器给它的 MAC 绑定一个固定 IP(DHCP 保留地址),或在那台机器上设静态 IP。最稳。"
Write-Host "  - 服务在 Mac:IP 老变多半是 Apple『私有 Wi-Fi 地址』轮替 → 系统设置→Wi-Fi→详细信息→『私有 Wi-Fi 地址』改『固定』。"
Write-Host "  IP 真变了:重跑本命令、-ServerUrl 换成新地址即可。"
Write-Host ""
Write-Host "  不想用了:以管理员运行  powershell -ExecutionPolicy Bypass -File installers\kindle\uninstall.ps1"
