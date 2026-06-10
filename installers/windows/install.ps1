<#
Kindle Dashboard — one-command Windows server install. Idempotent: safe to re-run anytime.
Mirrors installers/macos/install.sh phase-for-phase (no menubar / Apple-reminders / Codex-quota phases).

What it does:
  1. Check Python >= 3.10
  2. Create venv (if missing) + install deps (incl. tzdata on Windows) + import self-check
  3. Detect Chrome/Chromium/Edge; offer Playwright bundled chromium if none
  4. Detect/install Node + ccusage (AI token counts; optional)
  5. Externalize config to %USERPROFILE%\.config\kindle-dashboard\config.yaml (survives re-clones)
  6. Fix server.timezone to the real local zone (only if still the Asia/Shanghai default)
  7. Idempotent config content: local device entry, display pages/style (only if unset)
  8. Windows Firewall inbound rule for the dashboard port (admin; skipped with guidance if not)
  9. Autostart: scheduled task "KindleDashboard" at logon, hidden window, no 72h execution limit
 10. Health self-check + print the token setup URL and Kindle frame URL

Usage (admin PowerShell recommended, needed for the firewall rule):
  powershell -ExecutionPolicy Bypass -File installers\windows\install.ps1
  -Yes = non-interactive: take the default answer at every prompt
#>
param([switch]$Yes)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
$TaskName = "KindleDashboard"

function Fail($m) { Write-Host "X $m" -ForegroundColor Red; exit 1 }
function Step($m) { Write-Host "==> $m" }
function Ask($prompt, $default) {
    if ($Yes) { Write-Host "  $prompt -> $default (auto)"; return $default }
    $a = Read-Host $prompt
    if ($a) { return $a } else { return $default }
}

$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)

# ---------- 1+2. Python + venv ----------
# If the venv already exists, never touch system Python (the WindowsApps `py`/`python`
# stubs can hang or open the Store, esp. in elevated sessions). Idempotent re-runs skip it.
if (-not (Test-Path $Py)) {
    Step "Checking Python..."
    $SysPy = $null
    foreach ($cand in @("py", "python")) {
        $cmd = Get-Command $cand -ErrorAction SilentlyContinue
        # skip the WindowsApps store stubs — they aren't a real interpreter
        if ($cmd -and $cmd.Source -notlike "*WindowsApps*") { $SysPy = $cmd.Source; break }
    }
    if (-not $SysPy) { Fail "Python not found (only Store stubs). Install Python 3.10+ from python.org and re-run." }
    $pyArgs = if ($SysPy -like "*py.exe") { @("-3") } else { @() }
    $ver = & $SysPy @pyArgs -c "import sys; print('%d.%d' % sys.version_info[:2])"
    if ([version]$ver -lt [version]"3.10") { Fail "Python $ver found; need >= 3.10." }
    Write-Host "  Python $ver ($SysPy)"
    Step "Creating virtualenv..."
    if (Test-Path (Join-Path $Repo ".venv")) { Remove-Item (Join-Path $Repo ".venv") -Recurse -Force }
    & $SysPy @pyArgs -m venv (Join-Path $Repo ".venv")
    if (-not (Test-Path $Py)) { Fail "venv creation failed." }
}
Step "Installing dependencies..."
& $Py -m pip install -q --upgrade pip 2>$null
& $Py -m pip install -q -r (Join-Path $Repo "server\requirements.txt")
& $Py -m pip install -q tzlocal      # installer-only: detect the local IANA timezone
& $Py -c "import fastapi,uvicorn,httpx,PIL,lunardate,jinja2,yaml; from zoneinfo import ZoneInfo; ZoneInfo('America/New_York')"
if ($LASTEXITCODE -ne 0) { Fail "Dependency self-check failed (zoneinfo/tzdata?). See output above." }
Write-Host "  Dependencies OK (incl. timezone data)"

# ---------- 3. Render engine ----------
Step "Checking render engine (Chrome/Chromium/Edge)..."
Set-Location $Repo
$chrome = & $Py -c "from server.render.pipeline import find_chrome; print(find_chrome())"
if (-not $chrome) {
    $ans = Ask "  No Chrome found. Download bundled Chromium via Playwright (~150MB, into the venv)? [Y/n]" "Y"
    if ($ans -notmatch '^[nN]') {
        & $Py -m playwright install chromium
        $chrome = & $Py -c "from server.render.pipeline import find_chrome; print(find_chrome())"
    }
    if (-not $chrome) { Fail "Still no render engine. Install Chrome or run: .venv\Scripts\python -m playwright install chromium" }
}
Write-Host "  Render engine: $chrome"

# ---------- 4. Node + ccusage (AI token counts) ----------
Step "Checking ccusage (AI token counts)..."
if (-not (Get-Command ccusage -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        $ans = Ask "  Node.js not found. Install Node LTS via winget (needed for ccusage token counts)? [Y/n]" "Y"
        if ($ans -notmatch '^[nN]') {
            winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
            # refresh PATH in this session so npm is callable right away
            $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        }
    }
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm -and (Test-Path "$env:ProgramFiles\nodejs\npm.cmd")) { $npm = "$env:ProgramFiles\nodejs\npm.cmd" }
    if ($npm) {
        Write-Host "  Installing ccusage globally (npm)..."
        & $npm install -g ccusage *> (Join-Path $Repo "data\ccusage-install.log")
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    }
}
if (Get-Command ccusage -ErrorAction SilentlyContinue) {
    Write-Host "  ccusage OK"
} else {
    Write-Host "  ! ccusage unavailable — AI page shows quota only, token counts stay 0 (install later: npm i -g ccusage)" -ForegroundColor Yellow
}

# ---------- 5. Config externalization ----------
Step "Config file..."
$Config = $env:KINDLE_CONFIG
if (-not $Config) { $Config = Join-Path $env:USERPROFILE ".config\kindle-dashboard\config.yaml" }
New-Item -ItemType Directory -Force (Split-Path -Parent $Config) | Out-Null
New-Item -ItemType Directory -Force (Join-Path $Repo "data") | Out-Null
if (Test-Path $Config) {
    Write-Host "  Using existing $Config"
} elseif (Test-Path (Join-Path $Repo "config.yaml")) {
    Copy-Item (Join-Path $Repo "config.yaml") $Config
    Write-Host "  Migrated in-repo config.yaml -> $Config"
} elseif (Test-Path (Join-Path $Repo "config.local.yaml")) {
    Copy-Item (Join-Path $Repo "config.local.yaml") $Config
    Write-Host "  Migrated in-repo config.local.yaml -> $Config"
} else {
    Copy-Item (Join-Path $Repo "config.example.yaml") $Config
    Write-Host "  Created from config.example.yaml -> $Config"
}

# ---------- 6+7. Timezone + idempotent config content ----------
Step "Configuring (timezone / local device / pages)..."
$tz = & $Py -c "import tzlocal; print(tzlocal.get_localzone_name())" 2>$null
if (-not $tz) {
    Write-Host "  ! Could not auto-detect timezone (tzutil says: $(tzutil /g))"
    $tz = Ask "  Enter an IANA timezone (e.g. America/Chicago), Enter to keep current" ""
}
$cfgScript = @'
import sys, yaml
path, tz, host = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as f:
    c = yaml.safe_load(f) or {}
srv = c.setdefault("server", {})
# timezone: only fix if still the shipped default (never clobber a user-set value)
if tz and srv.get("timezone", "Asia/Shanghai") == "Asia/Shanghai":
    srv["timezone"] = tz
    print(f"  timezone -> {tz}")
dev = c.setdefault("devices", {})
machines = dev.setdefault("machines", []) or []
if not any((m or {}).get("mode") == "local" for m in machines):
    machines.append({"name": host, "mode": "local", "platform": "auto"})
    dev["machines"] = machines
    print(f"  local device added: {host}")
disp = c.setdefault("display", {})
if not disp.get("pages"):
    disp["pages"] = ["home", "ai", "device"]
    print("  pages -> [home, ai, device]")
if not disp.get("style"):
    disp["style"] = "style_a"
with open(path, "w", encoding="utf-8") as f:
    yaml.safe_dump(c, f, allow_unicode=True, sort_keys=False)
'@
$cfgScript | & $Py - $Config $tz $env:COMPUTERNAME

# port from config
$Port = & $Py -c "import yaml,sys; print((yaml.safe_load(open(sys.argv[1], encoding='utf-8')) or {}).get('server',{}).get('port',8585))" $Config

# ---------- 8. Firewall ----------
Step "Windows Firewall (inbound TCP $Port for the Kindle)..."
if (Get-NetFirewallRule -DisplayName "Kindle Dashboard" -ErrorAction SilentlyContinue) {
    Write-Host "  Rule already present"
} elseif ($IsAdmin) {
    New-NetFirewallRule -DisplayName "Kindle Dashboard" -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $Port -Profile Private, Domain | Out-Null
    Write-Host "  Allowed inbound TCP $Port (Private/Domain profiles)"
} else {
    Write-Host "  ! Not admin — firewall rule NOT created. The Kindle cannot reach the server until you run (as admin):" -ForegroundColor Yellow
    Write-Host "    New-NetFirewallRule -DisplayName 'Kindle Dashboard' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private,Domain"
}

# ---------- 9. Autostart (scheduled task) ----------
Step "Autostart (scheduled task '$TaskName')..."
$wrapper = Join-Path $Repo "data\run_server.ps1"
@"
# Auto-generated by installers\windows\install.ps1 — runs the dashboard, appends output to data\service.log
Set-Location '$Repo'
`$env:KINDLE_CONFIG = '$Config'
& '$Py' -m server.run *>> '$(Join-Path $Repo "data\service.log")'
"@ | Set-Content $wrapper -Encoding UTF8

# stop any previous instance (ours only: command line contains server.run under this repo's venv)
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*server.run*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$wrapper`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
# ExecutionTimeLimit Zero = no 72h kill (the Windows default would stop the server every 3 days)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "  Registered + started (runs at every logon, no execution time limit)"

# ---------- 10. Health check + URLs ----------
Step "Waiting for the service..."
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $h = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2
        if ($h.status -eq "ok") { $ok = $true; break }
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $ok) {
    Write-Host "X Service did not come up. Last log lines:" -ForegroundColor Red
    Get-Content (Join-Path $Repo "data\service.log") -Tail 25 -ErrorAction SilentlyContinue
    exit 1
}
$token = & $Py -c "import yaml,sys; print((yaml.safe_load(open(sys.argv[1], encoding='utf-8')) or {}).get('server',{}).get('access_token',''))" $Config
# LAN IP of the default-route interface (skips ZeroTier/VPN adapters with no default route)
$ifIndex = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
    Sort-Object RouteMetric | Select-Object -First 1).InterfaceIndex
$LanIp = (Get-NetIPAddress -InterfaceIndex $ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Select-Object -First 1).IPAddress
if (-not $LanIp) { $LanIp = "127.0.0.1" }

Write-Host ""
Write-Host "OK Kindle Dashboard is running." -ForegroundColor Green
Write-Host ""
Write-Host "  Settings page:  http://${LanIp}:$Port/setup?token=$token"
Write-Host "  Kindle frame:   http://${LanIp}:$Port/kindle/frame.png"
Write-Host "  Config file:    $Config"
Write-Host "  Logs:           $Repo\data\service.log"
Write-Host ""
Write-Host "  ! Give this PC a fixed IP (router DHCP reservation for $LanIp) — the Kindle fetches from it." -ForegroundColor Yellow
Write-Host "  Next: open the settings page to pick your Kindle model, weather city, and connect Microsoft To Do."
Write-Host "  Then set up the Kindle:  powershell -ExecutionPolicy Bypass -File installers\kindle\install.ps1 -ServerUrl http://${LanIp}:$Port"
Write-Host "  Uninstall service:  Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false  (config stays)"
