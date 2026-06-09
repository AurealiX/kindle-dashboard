<#
Kindle one-command setup (Windows version): push start/stop, write the server address, install autostart, start the display.
Mirrors installers/kindle/install.sh for macOS/Linux — **same logic**; only the platform commands differ
(local IP detection / configuring the USB adapter with netsh / using Windows' built-in ssh+scp). The scripts pushed to the Kindle and the Kindle-side logic are byte-for-byte unchanged.

Prerequisites: Kindle jailbroken + USBNetwork (SSH) enabled; Windows 10+ built-in OpenSSH client; configuring the USB adapter needs admin.
Usage (right-click PowerShell -> "Run as administrator"):
  powershell -ExecutionPolicy Bypass -File installers\kindle\install.ps1
  Optional params: -KindleIp 192.168.15.244  -ServerUrl http://<PC-IP>:8585  -Interval 20
WARN: This script has not yet been verified on real hardware (Windows + Kindle); on first use, follow the prompts to troubleshoot.
#>
param(
  [string]$KindleIp  = "192.168.15.244",
  [string]$ServerUrl = "",
  [int]$Interval     = 0
)
$ErrorActionPreference = "Stop"
$KDIR = $PSScriptRoot
# Track the USB adapter this run temporarily gave a static IP, and restore it to automatic (DHCP) when done (success or failure) —
# Windows netsh is a persistent config (unlike macOS ifconfig, which auto-recovers on unplug); without restoring, the adapter would be left static.
$script:UsbAdapter = $null
function Restore-UsbRoute {
  if ($script:UsbAdapter) {
    try { netsh interface ipv4 set address name="$script:UsbAdapter" dhcp | Out-Null } catch {}
    Write-Host "  (restored the temporarily-configured USB adapter '$script:UsbAdapter' to automatic IP)"
    $script:UsbAdapter = $null
  }
}
function Fail($m){ Restore-UsbRoute; Write-Host "X $m" -ForegroundColor Red; exit 1 }

# 0. Prereqs: ssh/scp present + admin check
if (-not (Get-Command ssh  -ErrorAction SilentlyContinue)) { Fail "ssh not found. Install the built-in Windows OpenSSH client: Settings -> Apps -> Optional features -> Add 'OpenSSH Client', then re-run." }
if (-not (Get-Command scp  -ErrorAction SilentlyContinue)) { Fail "scp not found (same as above, install the OpenSSH client)." }
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)

# 1. Auto-detect the server address (local LAN IP, home subnets preferred; won't wrongly pick 198.18.* etc. when a proxy is on)
if (-not $ServerUrl) {
  $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
        Sort-Object @{Expression={ switch -Wildcard ($_.IPAddress) { '192.168.*'{0} '10.*'{1} '172.*'{2} default{9} } }} |
        Select-Object -First 1 -ExpandProperty IPAddress
  if (-not $ip) { $ip = "127.0.0.1" }
  $ServerUrl = "http://${ip}:8585"
}
Write-Host "Kindle: $KindleIp    Server address: $ServerUrl"

# 2. Kindle image-fetch interval (seconds): param first, otherwise ask interactively, default 20 (<5 treated as invalid)
if ($Interval -lt 5) {
  $ans = Read-Host "==> How often should the Kindle fetch a new image? Shorter = more real-time, more battery. Common 10/20/30/60, Enter defaults to 20"
  if ($ans -match '^[0-9]+$' -and [int]$ans -ge 5) { $Interval = [int]$ans } else { $Interval = 20 }
}
Write-Host "   Refresh interval: ${Interval}s"

# Windows doesn't broadcast mDNS by default (no Bonjour), so no .local fallback is written; a fixed IP is more reliable (see docs/install.md)
$ServerUrlAlt = ""

# 3. USB network: set the Kindle's USB adapter to 192.168.15.201/24 (symmetric with ensure_usb_route in the .sh)
function Ensure-UsbRoute {
  if ($KindleIp -ne "192.168.15.244") { return $true }                 # only the standard USBNetwork address needs this
  if (Test-Connection -Count 1 -Quiet $KindleIp -ErrorAction SilentlyContinue) { return $true }  # already reachable, skip (idempotent)
  Write-Host "==> USB network not reachable, auto-configuring the local USB interface..."
  if (-not $IsAdmin) { Write-Host "   ! Configuring the adapter needs admin. Right-click PowerShell -> 'Run as administrator' and re-run this script." -ForegroundColor Yellow; return $false }
  # Only configure adapters that are [connected (Up)] and got a 169.254 (APIPA) address — that's likely the just-plugged-in Kindle USB adapter.
  # Don't touch disconnected WLAN/Bluetooth/virtual adapters (they also often show 169.254; misconfiguring them would break your reconnection).
  $upNames = @((Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' }).Name)
  $cands = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress -like '169.254.*' -and $upNames -contains $_.InterfaceAlias }
  if (-not $cands) {
    Write-Host "   ! No [connected] Kindle USB adapter found. Most common cause:" -ForegroundColor Yellow
    Write-Host "     The Kindle is currently in [USB mass-storage mode] (shows in Windows as a 'Kindle Internal Storage USB Device' disk), not network mode."
    Write-Host "     -> On the Kindle, launch USBNetwork via KUAL to turn it into a network device; if Windows sees it as an unknown device, install the 'Remote NDIS Compatible Device' driver in Device Manager. Then re-run this command."
    return $false
  }
  foreach ($c in $cands) {
    $alias = $c.InterfaceAlias
    Write-Host "   Detected connected candidate USB adapter '$alias', temporarily setting 192.168.15.201 (only this one, won't affect your internet; restored when done)..."
    try { netsh interface ipv4 set address name="$alias" static 192.168.15.201 255.255.255.0 | Out-Null } catch {}
    $script:UsbAdapter = $alias    # remember it, restore to automatic when the script ends
    Start-Sleep -Seconds 2
    if (Test-Connection -Count 1 -Quiet $KindleIp -ErrorAction SilentlyContinue) { Write-Host "   OK USB network reachable" -ForegroundColor Green; return $true }
  }
  return $false
}
if (-not (Ensure-UsbRoute)) {
  Write-Host "! USB network still not reachable. Check: (1) is the Kindle recognized in Device Manager as a 'Network adapter / USB RNDIS' (if not, install the RNDIS driver) (2) use a data-capable cable (3) Kindle has USBNetwork enabled. To use WiFi instead: add params -KindleIp <KindleWiFiIP> -ServerUrl http://<PC-IP>:8585" -ForegroundColor Yellow
}

# 4. SSH push + install. Windows OpenSSH doesn't support ControlMaster connection reuse, so **it'll prompt for the password a few times** (jailbreak default mario)
$O = @("-o","StrictHostKeyChecking=no")
Write-Host "Note: you'll be asked for the Kindle's root password next (jailbreak default mario; use yours if you changed it). A few prompts is normal."
& ssh @O "root@$KindleIp" "echo connected"
if ($LASTEXITCODE -ne 0) { Fail "Cannot SSH to the Kindle. Confirm the USB network is reachable and the Kindle has USBNetwork enabled." }

Write-Host "==> Backing up the old version (if any)..."
& ssh @O "root@$KindleIp" "if [ -f /mnt/us/start.sh ] || [ -f /mnt/us/stop.sh ]; then mkdir -p /mnt/us/kindle-dash-backup; cp /mnt/us/start.sh /mnt/us/kindle-dash-backup/ 2>/dev/null; cp /mnt/us/stop.sh /mnt/us/kindle-dash-backup/ 2>/dev/null; cp /etc/crontab/root /mnt/us/kindle-dash-backup/crontab.root 2>/dev/null; echo '  backup ok'; else echo '  (no old version, skipping)'; fi"

Write-Host "==> Pushing scripts..."
& scp @O (Join-Path $KDIR "start.sh") (Join-Path $KDIR "stop.sh") "root@${KindleIp}:/mnt/us/"
if ($LASTEXITCODE -ne 0) { Fail "scp push of start.sh/stop.sh failed." }

Write-Host "==> Writing config, installing autostart, starting..."
# Single-line sh command (semicolon-chained) to avoid quoting pitfalls passing multiline args from Windows; runs on the Kindle's busybox sh
$remote = "echo 'SERVER_URL=$ServerUrl' > /mnt/us/dashboard.conf; " +
          "echo 'SERVER_URL_ALT=$ServerUrlAlt' >> /mnt/us/dashboard.conf; " +
          "echo 'INTERVAL=$Interval' >> /mnt/us/dashboard.conf; " +
          "chmod +x /mnt/us/start.sh /mnt/us/stop.sh; " +
          "/usr/sbin/mntroot rw 2>/dev/null || true; " +
          "grep -v '/mnt/us/start.sh' /etc/crontab/root > /tmp/cr.tmp 2>/dev/null && mv /tmp/cr.tmp /etc/crontab/root; " +
          "echo '@reboot sleep 30 && /mnt/us/start.sh # kindle-dashboard' >> /etc/crontab/root; " +
          "/usr/sbin/mntroot ro 2>/dev/null || true; " +
          "command -v fbink >/dev/null 2>&1 || echo 'WARN: fbink not found, screen writes will fail -- install fbink via KUAL/jailbreak tools and re-run'; " +
          "setsid /mnt/us/start.sh < /dev/null > /mnt/us/dashboard.log 2>&1 &" +
          " echo started"
& ssh @O "root@$KindleIp" $remote

Restore-UsbRoute   # restore the temporarily-configured USB adapter to automatic IP

Write-Host ""
Write-Host "OK Done. The Kindle should start showing the dashboard (landscape, top edge to the right)." -ForegroundColor Green
Write-Host "  After this, just save config changes in the web page — no need to touch the Kindle again."
Write-Host ""
Write-Host "! Important: the Kindle fetches from the fixed address $ServerUrl — once the IP of [the machine hosting the dashboard service] changes, the dashboard stops updating. Pin it:" -ForegroundColor Yellow
Write-Host "  - Service on NAS / always-on host: bind a fixed IP to its MAC in the router (DHCP reservation), or set a static IP on that machine. Most reliable."
Write-Host "  - Service on a Mac: the IP changes often, usually due to Apple's 'Private Wi-Fi Address' rotation -> System Settings->Wi-Fi->Details->'Private Wi-Fi Address' set to 'Fixed'."
Write-Host "  IP really changed: re-run this command with -ServerUrl set to the new address."
Write-Host ""
Write-Host "[Escape hatch] If the dashboard occupies the screen and you can't connect (no USBNetwork, no WiFi): plug the Kindle into any computer" -ForegroundColor Cyan
Write-Host "  (default USB mass-storage mode, no USBNetwork/WiFi needed), create an empty file dashboard.off at the drive root, reboot to return to normal; delete it to restore the dashboard."
Write-Host ""
Write-Host "  Done with it? Run as admin:  powershell -ExecutionPolicy Bypass -File installers\kindle\uninstall.ps1"
