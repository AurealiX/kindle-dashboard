# Installation guide (detailed)

> See the [README](../README.md) for an overview. This doc adds per-data-source config, Kindle prerequisites, troubleshooting, and verification status.

## 1. Mac service

```bash
bash installers/macos/install.sh
```

Run the service manually (for debugging):

```bash
.venv/bin/python -m server.run     # reads the port from config.yaml, binds 0.0.0.0
```

- Config file: **outside the repo** at `~/.config/kindle-dashboard/config.yaml` (first generated from `config.example.yaml`; see "Config file location" below)
- Logs: `data/*.log` (service / menubar / codex-quota / reminders); **auto-rotated by the service** — truncated to the last 1MB past 5MB, so long runs won't fill the disk and need no manual cleanup.
- Changing the port needs a service restart; all other config hot-reloads on save from the web page
- **Access token** (keeps others on the same WiFi out of the settings page): auto-generated on first start, stored in `server.access_token` of `config.yaml`; after `install.sh` finishes it prints `http://<IP>:port/setup?token=...` — **open the settings page via this token link** (or click "Open settings" in the menu bar). `/api/*` and preview require the token; **Kindle image fetch (`/kindle/frame.png`), device reporting, and `/health` are exempt**. A blank token = no auth (not recommended).

The installer handles dependencies automatically and asks you two things along the way:
- **Render engine**: when no Chrome is detected, it asks whether to auto-download a bundled chromium (playwright, ~150MB, into the venv, not touching your system). Just pick Y — no need to install Chrome yourself.
- **AI usage stats**: asks whether to enable (see "AI usage" below); enabling auto-detects Node + ccusage and installs what's missing, so you don't have to.

**Menu-bar app**: after install, the macOS status bar shows only a small Kindle icon, no "dashboard" text. Click it to see run status, current version, open the settings page, restart/start/stop the service, and **check for updates**; the "Start at login" checkbox controls whether the main service auto-starts at next login. The installer generates a local `LSUIElement` app bundle that only shows in the status bar, not as a Python icon in the Dock. It depends on `rumps`, which install.sh installs automatically (if an old venv lacks it, re-run install.sh to add it).

**Config file location**: the real config lives **outside the repo** at `~/.config/kindle-dashboard/config.yaml` (override with the `KINDLE_CONFIG` env var). This way upgrades / reinstalls / delete-and-reclone **never lose settings**; if an old version put `config.yaml` inside the repo, it's auto-migrated on first start.

### Updating a deployed service (when there's a new code version)
Config changes hot-reload on save; but **Python code updates require restarting the process** to take effect. Two ways:
- **One-click from the menu bar (recommended)**: click the status-bar icon → **Check for updates** → if a new version exists, click "Upgrade" to auto `git pull --ff-only` + restart (config is outside the repo, so upgrades don't touch your settings).
- **Command line**: `cd ~/kindle-dashboard && git pull`, then run `bash installers/macos/restart.sh` (restarts main service + menu bar together), or re-run `bash installers/macos/install.sh` (update deps + restart + self-check).
- Verify: open `http://<your-IP>:port/health` in a browser.
> ⚠️ Don't run the service directly on a network share (SMB/NFS, `/Volumes/...` on Mac): the venv can't be built cleanly on a network drive. Always copy the project to a local disk (e.g. `~/kindle-dashboard`) before installing/updating.
> Online upgrade requires the dashboard to have been installed via `git clone` (in a non-git directory the menu bar will say online upgrade isn't possible — use the command line to overwrite instead).

## 2. Per-data-source configuration

### Weather (QWeather)
1. Register as a free developer at [QWeather](https://dev.qweather.com/)
2. Get your **API Key** and **dedicated API Host** (like `xxx.re.qweatherapi.com`)
3. Look up the city **LocationID** (e.g. Beijing `101010100`)
4. Fill them into the settings page "Weather" → the home page shows weather

### Home Assistant (printer / more devices)
1. HA user profile page → create a **Long-Lived Access Token**
2. Fill the address + token into the settings page "Home Assistant"
3. In "3D printer" click "Scan" to select the printer → after saving, the printer page appears

### AI usage (ccusage)
- **Local collection, zero config, no middleware**: answer "enable AI usage" at install time → it auto-installs Node + [ccusage](https://github.com/ryoppippi/ccusage) and sets `ai_usage.enabled` true; each round the server runs `ccusage claude/codex daily --json` to read local logs (see `server/sources/ccusage_cli.py`). Whichever machine runs the dashboard service is the one whose usage is read.
- "Quota" (5h/weekly windows) is a separate thing (ccusage doesn't provide it); see the "AI quota" section below; when not enabled, the AI page shows quota 0% (honest degradation).

### AI quota (Claude 5h/weekly + Codex 5h/weekly)
Shows Claude / Codex quota usage % on the AI page. **Push model**: collected on the machine running Claude Code / Codex CLI, POSTed to the dashboard `/api/rate-limits` (the dashboard service itself can't obtain this data — devices must deliver it).

- **Claude** (official mechanism, stable): rides Claude Code's **statusLine** — Claude Code pipes a JSON containing `rate_limits` into your configured status-line command via stdin. The bundled script reads that and POSTs it to the dashboard. **This works on any OS Claude Code runs on, including Windows — no launchd, no daemon.**
  - **macOS**: `installers/macos/enable_quota.sh` checks `~/.claude/settings.json` — if no statusLine is configured, it backs up and writes one pointing at `installers/macos/quota/claude_statusline.py`; if you already customized it, it won't overwrite, and prints guidance to copy the POST block into your own status line (the `# >>> push quota` to `# <<<` section in the script).
  - **Windows**: use `installers/windows/quota/claude_statusline.py`. Set the push URL in `installers/windows/quota/quota.conf`, then point your status line at the script in `~/.claude/settings.json`:
    ```json
    "statusLine": {
      "type": "command",
      "command": "\"<repo>\\.venv\\Scripts\\python.exe\" \"<repo>\\installers\\windows\\quota\\claude_statusline.py\"",
      "refreshInterval": 180
    }
    ```
    The status bar shows `Ctx · 5h · Wk` and pushes the quota (throttled by `KINDLE_QUOTA_PUSH_INTERVAL`). The script is pure stdlib and uses `curl` (shipped in Windows 10/11).
- **Codex** (⚠️ non-public endpoint, may break): `codex_quota.py` reads `~/.codex/auth.json` and calls `chatgpt.com/backend-api/wham/usage`, reported on a launchd timer. `wham/usage` is an internal, undocumented OpenAI endpoint — **an official change can break it at any time** (doesn't affect Claude). Reaching chatgpt.com from some regions needs a proxy: fill in **Codex proxy** in the settings page "AI usage" (or set `ai_usage.codex_proxy: http://127.0.0.1:7897` in config). Codex quota is **macOS-only** for now.

How to enable (run on the Mac that hosts the dashboard, in the project directory):
- **At install time**: `install.sh` asks "Enable AI quota?" + "How often should Codex report (seconds)?"; pick `y` and it's set up automatically.
- **Add later**: `bash installers/macos/enable_quota.sh`. The script also sets `ai_usage.enabled` true to avoid having quota collection installed while the AI page stays hidden.
- **Disable**: `bash installers/macos/disable_quota.sh` (removes the Codex launchd job; undo Claude's statusLine yourself per the printed guidance).
- **Intervals**: `ai_usage.codex_quota_interval` (seconds, launchd) / `ai_usage.claude_quota_interval` (seconds, statusLine throttle); re-run `enable_quota.sh` after changing.

### Device monitoring (Win/Linux/Mac)
**The dashboard host (this Mac)**: answer "enable local performance monitoring" at install time (auto-adds one `local` device), or add a "local read" machine later in the settings page "Device monitoring".

**Another machine (NAS / Linux / Mac), pick one of three:**
- **Local read (local)**: only the host running the service, zero extra install.
- **Push (agent, recommended, no password shared)**: copy the command at the bottom of the settings page "Device monitoring" card and run it once on the target machine:
  ```sh
  curl -fsSL http://<dashboard-IP>:<port>/agent/install.sh | sh -s -- http://<dashboard-IP>:<port> 30
  ```
  After install it pushes every 30 seconds (change the trailing number for the interval); the target machine appears in the settings page "Discovered devices" — click to add and rename it.
  When the settings page generates this command, **the dashboard-address dropdown has an `Xxx.local:port` option** — pick it if the target supports mDNS (most Mac/Linux) to dodge Mac IP drift (IP changes, name doesn't); use the IP address for devices without mDNS.
  Autostart: Linux uses `@reboot` cron, macOS uses launchd. Uninstall: `... | sh -s -- uninstall`.
  **Windows**: the settings page also gives a PowerShell command (`iwr .../agent/install.ps1 ... | ...`), autostart via a "Scheduled Task" (on login); uninstall by replacing the trailing arg with `uninstall`.
  **The interval is set by the target machine's agent (at install time) and can't be changed from the settings page** (unlike the server-side interval for local/SSH).
- **Pull (SSH)**: the server SSHes in and reads, zero install on the target; password login needs `sshpass` on the host — a passwordless key is recommended.
- Pick the right `platform` (auto/linux/macos/windows); you can rename and select only some metrics to show.

Collection scripts: `server/sources/collectors/` (linux.sh / macos.sh / windows.ps1), reused across local read / SSH pull / push agent.
Push agent: `installers/push-agent/` (`install_agent.sh` is served by the dashboard's `/agent/install.sh`; `push_agent.sh` loops collect + POST).

### Reminders (Apple, macOS only)
Show the local "Reminders" app (including iPhone items synced via iCloud) on the dashboard. How it works: a background agent reads Reminders.app via JXA every 5 minutes and POSTs to `/api/apple-sync`.

How to enable (either way; both run in a terminal on the Mac hosting the dashboard, in the project directory):
- **At install time**: `install.sh` asks "Enable reminders sync?"; pick `y` and it's set up automatically.
- **Add later**: copy the command from the settings page "Reminders" card and run it:
  ```bash
  bash installers/macos/enable_reminders.sh
  ```
- **Disable**: `bash installers/macos/disable_reminders.sh`

The first run pops "Allow access to Reminders" — **you must click Allow**, or it can't read them. If you accidentally denied: System Settings → Privacy & Security → Reminders, tick Terminal/osascript, then re-run the command.

> Why not a web toggle? Because it needs a local background agent + a one-time system authorization, and only a foreground terminal run can surface the auth dialog; a web toggle would become "shown on, actually no data". So a one-line command does it all; install/uninstall state follows whether the agent is running (settings-page badge).

## 3. Kindle prerequisites

1. **Jailbreak**: find the method for your firmware version (this project does not include jailbreak tools)
2. **Enable USBNetwork**: let the Kindle provide SSH over USB (default IP is usually `192.168.15.244`)
3. **Install fbink**: required to write the screen, usually provided with KUAL/jailbreak toolkits
4. Use a **data-capable** USB cable (not a charge-only cable)
5. **SSH root password**: required at install time. Jailbreak packages (KUAL/USBNetwork etc.) **commonly default to `mario`**; if you changed it during jailbreak, use yours. `install.sh` also reminds you of this at runtime.

Then on the host:

```bash
sh installers/kindle/detect.sh [KINDLE_IP]      # detect: USB connected + SSH reachable
sh installers/kindle/install.sh [KINDLE_IP] [SERVER_URL] [INTERVAL]
sh installers/kindle/uninstall.sh [KINDLE_IP]   # one-command restore
```

**Windows host** (Kindle plugged into a Windows PC to push images): use the PowerShell version, **right-click PowerShell → "Run as administrator"** (configuring the USB network adapter needs admin; the built-in OpenSSH client on Windows 10+ must be installed):
```powershell
powershell -ExecutionPolicy Bypass -File installers\kindle\install.ps1     # one-command image push (optional -KindleIp / -ServerUrl / -Interval)
powershell -ExecutionPolicy Bypass -File installers\kindle\uninstall.ps1   # one-command restore to a normal e-reader
```
> The logic matches the .sh version (configures the USB adapter with `netsh`, uses Windows' built-in `ssh`/`scp`). `.gitattributes` forces `*.sh`=LF and `*.ps1`=BOM+CRLF to keep a Windows clone from corrupting the scripts (a `.ps1` without BOM gets read as GBK by PS5, garbling Chinese).
>
> **Two ways to connect (the settings-page "Service" card's flashing box has a Kindle-IP field; fill it and the full command is assembled for you)**:
> - **Option 1: USB** (default `192.168.15.244`): plug the Kindle into the PC. ⚠️ Two prerequisites — ① **enable USBNetwork on the Kindle first** (KUAL; **it turns off on every reboot and defaults to USB mass-storage mode**, so Windows sees it as a disk, not a NIC) ② Windows recognizes the Kindle as a "network adapter / RNDIS" (if it shows as an unknown device, install the "Remote NDIS Compatible Device" driver in Device Manager). These two are inherent hurdles for plugging a jailbroken Kindle into Windows.
> - **Option 2: WiFi (recommended, no driver install)**: connect the Kindle to WiFi → find its IP in the router admin → enter it in the flashing box (or `-KindleIp <IP>`). When the script detects a non-`.244` address it **skips USB config and goes straight to WiFi SSH**, identical on Win/Mac/Linux, no RNDIS driver involved. **The Kindle still needs SSH on (USBNetwork's dropbear also listens over WiFi).**
> - ⚠️ Real-device verification status: `.ps1` encoding/adapter-restore verified; the full flashing flow is pending further verification due to USBNetwork mode issues.

`install.sh` pushes `start.sh`/`stop.sh`, writes the server address to `/mnt/us/dashboard.conf`, adds an `@reboot` autostart (tagged `# kindle-dashboard` for precise removal on uninstall), and starts the display.

**Refresh interval**: `install.sh` asks at runtime "how often should the Kindle fetch a new image (seconds)" — common values 10/20/30/60, Enter defaults to 20, written as `INTERVAL` in `dashboard.conf` (can also be passed as the third argument, e.g. `... [SERVER_URL] 30`; non-interactive defaults to 20, <5s auto-falls back to 20). Note the two distinct intervals:
- **`INTERVAL` (Kindle fetch interval)**: set at flash time, how often the Kindle fetches a new image. Changing it requires re-running `install.sh`; the web page can't change it.
- **`page_interval` (server-side rotation interval)**: how many seconds the dashboard waits between flipping pages, configurable anytime in the settings page.

**Keep the server IP stable (critical)**: the Kindle fetches from a fixed address — **once the IP of the machine hosting the dashboard changes, the Kindle can't fetch and the dashboard stops updating**. Two cases by where the service runs:

- **Service on NAS / always-on host** (NAS deploy): a NAS is usually wired and its MAC doesn't change, so **bind a fixed IP to its MAC in the router (DHCP reservation), or set a static IP on the NAS**. Bind once and it's stable — least hassle.
- **Service on a Mac**: a Mac's IP changes often, **mainly because of Apple's "Private Wi-Fi Address" (MAC randomization)** — defaulting to "Rotating", the Mac periodically swaps to a random MAC; the router tracks leases by MAC, so when the MAC changes the IP follows. **Fix: System Settings → Wi-Fi → current network "Details…" → "Private Wi-Fi Address" from "Rotating" to "Fixed"** (for extra stability also bind the IP in the router, or set a manual IP in TCP/IP).
  - ❌ Don't rely on router MAC binding alone: as long as "Private Wi-Fi Address" is still "Rotating", the MAC keeps changing and the binding is useless — you must switch to "Fixed" first.
- **The IP really changed**: re-run `install.sh` (or the Kindle flash command from the settings page) with `SERVER_URL` set to the new address.
- Note: the old `.local` (mDNS) fallback address has been removed — it only held when "the service runs on this machine" (when the service is on a NAS it computes the local hostname, which is wrong), and mainstream jailbroken Kindles (busybox) can't resolve `.local` at all.

**Screen resolution (model)**: the settings page "Service" has a **Kindle model** dropdown — pick your model (basic 6″ / Paperwhite 3-4 / PW5 / PW12·Oasis / Scribe) and the server renders a crisp image at that model's native resolution — high-PPI models are no longer upscaled and blurry.
- How it works: styles are designed only against the base canvas **landscape 800×600**; at render time Chrome's `--force-device-scale-factor` **vector-scales** the same layout to the target resolution (fonts/lines stay sharp when enlarged, zero CSS changes). See `docs/multi-resolution-spec.md`.
- For the 6″ basic, just pick the first option (= current behavior, unchanged). Unsure of the model: check the back of the device or "Settings → Device Info".
- Your model not in the list → pick "Custom" and manually enter the **landscape resolution** (= portrait width/height swapped, e.g. for a PW5 whose portrait is 1236×1648, enter width 1648, height 1236).
- A few non-4:3 models: scaled proportionally + white-background centered (letterbox), no cropping or distortion; pixel-perfect fill requires a per-style variant (P2).
- The Kindle's `fbink` blits the image to the screen at its actual size, so a server-side native-resolution image fits exactly — **no Kindle-side changes needed**.

## 4. Troubleshooting

| Symptom | Check |
|---|---|
| Render fails / blank screen | Confirm Chrome/Chromium is installed; or set `CHROME_BIN` to the executable |
| Chinese shows as boxes | Install CJK fonts (Linux: `fonts-noto-cjk`; Mac ships PingFang, usually fine; Windows ships Microsoft YaHei) |
| Can't connect to the Kindle | Run `detect.sh`; confirm jailbreak + USBNetwork + data cable; default IP `192.168.15.244`. On Windows, the Kindle showing as a disk = USBNetwork not on (turn it on, on the Kindle) or missing RNDIS driver; or switch to WiFi (enter the Kindle's WiFi IP) |
| **Dashboard occupies the screen and you can't connect to the Kindle (looks bricked)** | 🛟 Escape hatch: plug the Kindle into any computer (default USB mass-storage mode, **no USBNetwork/WiFi needed**), create an empty file `dashboard.off` at the drive root, reboot the Kindle to return to normal; delete that file to restore the dashboard. `start.sh` checks this file first at boot |
| Kindle doesn't refresh the screen | Missing `fbink`; install via KUAL/jailbreak tools |
| Kindle clock frozen (Docker) | Add `init: true` to compose (already built in); no such issue running natively |
| Devices page empty | Confirm the machine is configured and collection succeeded; push devices need the agent to have reported |

## 5. Verification status (honest checklist)

**Automated tests (42 items, `python3 -m pytest tests/ -q`)**:
- config schema/loading/validation/redacted-save, data contract, data integration
- render pipeline real output (degraded + real data), style scheduling
- Linux local collection end-to-end, all main-service APIs, settings page + live preview (verified with real Chrome screenshots)

**Pending real-device verification**:
- macOS / Windows collection scripts (`collect_macos.sh` / `collect_windows.ps1`)
- SSH pull mode (esp. password login needing `sshpass`; Windows target SSH)
- Mac launchd install (`installers/macos/`)
- Full Kindle detect/install/uninstall flow (`installers/kindle/`, needs a real Kindle)
