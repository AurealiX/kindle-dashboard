<#
Kindle one-command uninstall/restore (Windows version): stop the dashboard, remove autostart, delete scripts and images, restore the system UI — like it was never installed.
Mirrors installers/kindle/uninstall.sh for macOS/Linux; same logic. The Kindle-side commands are byte-for-byte unchanged.
Usage (right-click PowerShell -> "Run as administrator", needed to configure the USB adapter):
  powershell -ExecutionPolicy Bypass -File installers\kindle\uninstall.ps1 [-KindleIp 192.168.15.244]
WARN: Not yet verified on real hardware (Windows + Kindle).
#>
param([string]$KindleIp = "192.168.15.244")
$ErrorActionPreference = "Stop"
# A USB adapter temporarily given a static IP is restored to automatic when done (success or failure) (Windows netsh is persistent, so it must be restored explicitly).
$script:UsbAdapter = $null
function Restore-UsbRoute {
  if ($script:UsbAdapter) {
    try { netsh interface ipv4 set address name="$script:UsbAdapter" dhcp | Out-Null } catch {}
    Write-Host "  (restored the temporarily-configured USB adapter '$script:UsbAdapter' to automatic IP)"
    $script:UsbAdapter = $null
  }
}
function Fail($m){ Restore-UsbRoute; Write-Host "X $m" -ForegroundColor Red; exit 1 }

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { Fail "ssh not found. Install the built-in Windows OpenSSH client (Settings -> Apps -> Optional features -> OpenSSH Client)." }
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)

# USB network: symmetric with install.ps1, auto-configures the Kindle USB adapter to 192.168.15.201/24
function Ensure-UsbRoute {
  if ($KindleIp -ne "192.168.15.244") { return $true }
  if (Test-Connection -Count 1 -Quiet $KindleIp -ErrorAction SilentlyContinue) { return $true }
  Write-Host "==> USB network not reachable, auto-configuring the local USB interface..."
  if (-not $IsAdmin) { Write-Host "   ! Configuring the adapter needs admin. Right-click PowerShell -> 'Run as administrator' and re-run." -ForegroundColor Yellow; return $false }
  # Only configure [connected (Up)] 169.254 adapters (that's the Kindle USB), don't touch disconnected WLAN/Bluetooth/virtual adapters.
  $upNames = @((Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' }).Name)
  $cands = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress -like '169.254.*' -and $upNames -contains $_.InterfaceAlias }
  if (-not $cands) {
    Write-Host "   ! No [connected] Kindle USB adapter found. The Kindle is probably still in [USB mass-storage mode] (shows as a disk), not network mode." -ForegroundColor Yellow
    Write-Host "     -> On the Kindle, launch USBNetwork via KUAL and re-run; if Windows sees it as an unknown device, install 'Remote NDIS Compatible Device' in Device Manager."
    return $false
  }
  foreach ($c in $cands) {
    $alias = $c.InterfaceAlias
    Write-Host "   Detected connected candidate USB adapter '$alias', temporarily setting 192.168.15.201 (restored when done)..."
    try { netsh interface ipv4 set address name="$alias" static 192.168.15.201 255.255.255.0 | Out-Null } catch {}
    $script:UsbAdapter = $alias
    Start-Sleep -Seconds 2
    if (Test-Connection -Count 1 -Quiet $KindleIp -ErrorAction SilentlyContinue) { Write-Host "   OK USB network reachable" -ForegroundColor Green; return $true }
  }
  return $false
}
if (-not (Ensure-UsbRoute)) { Write-Host "! USB network still not reachable (troubleshoot as in install.ps1); to use WiFi instead: add param -KindleIp <KindleWiFiIP>" -ForegroundColor Yellow }

Write-Host "Note: you may be asked for the Kindle's root password next (jailbreak default mario)."
Write-Host "==> Restoring the Kindle ($KindleIp)..."
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
if ($LASTEXITCODE -ne 0) { Fail "Cannot SSH to the Kindle." }

Restore-UsbRoute   # restore the temporarily-configured USB adapter to automatic IP

Write-Host ""
Write-Host "OK Restored: stopped dashboard, removed autostart, deleted scripts and images, restored the UI." -ForegroundColor Green
Write-Host "  Recommend rebooting the Kindle for a full reset (hold the power button ~40 seconds)."
