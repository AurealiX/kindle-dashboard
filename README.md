# Kindle Dashboard

> Turn a jailbroken Kindle into a configurable home info dashboard — two commands + one web page, no coding.

> 💡 **About the author**
> I have **no coding experience whatsoever**. **Every line of code in this project was written by AI (Claude Code)** — I only provided the requirements, system design, and real-device testing. If you can't code either, just follow the commands below step by step.

> 🪟 **Windows fork**: This is the Windows-friendly fork. The render engine (FastAPI + headless Chromium + Pillow) runs natively on Windows; Chrome/Chromium detection includes Windows paths. The Claude 5h/weekly quota is collected via Claude Code's `statusLine` hook (see [AI quota](#ai-quota-claude-5h--weekly) below) — no macOS-only mechanism required. The macOS menu-bar app and launchd autostart are not ported; run the service manually or wire up Task Scheduler.

---

⚠️ **Jailbreak disclaimer**: Jailbreaking carries risk. This project does **not** include jailbreak tools — it only handles what comes **after** the jailbreak.
🔒 **Credential safety**: Your weather key / HA token / SSH credentials are **stored locally only** (`config.yaml`) and never uploaded anywhere.

## 🚀 One-command deploy

Three steps, one command each, with one round of web-form clicking in between — no coding at all:

**① Install the service** (on an always-on computer — Mac, NAS, or Windows)

```bash
git clone <repo-url> kindle-dashboard && cd kindle-dashboard
bash installers/macos/install.sh
```

The script automatically: creates a virtualenv, installs dependencies, generates `config.yaml` from the example, installs autostart, and starts the service. When done it prints your **settings-page link** and **Kindle image URL**. It only asks you two things along the way (auto-download the render engine? enable AI usage?) — pressing Enter takes the defaults.

> On **Windows**, there is no one-command installer yet. Set it up manually:
> ```powershell
> py -3 -m venv .venv
> .\.venv\Scripts\python -m pip install -r server\requirements.txt
> .\.venv\Scripts\python -m playwright install chromium
> $env:KINDLE_CONFIG = "$PWD\config.local.yaml"
> .\.venv\Scripts\python -m server.run
> ```
> Then open `http://localhost:8585/setup?token=...` (the token is printed at startup and stored in `config.local.yaml`).

**② Configure via web** (point-and-click, WYSIWYG)

Open the token link printed at install time: `http://localhost:8585/setup?token=...` (or, on macOS, click the menu-bar icon → "Open settings"). Fill in by module: Weather, Device monitoring, Home Assistant, Pages & styles, **UI language (中/EN)** — with a **live preview** on the right. Saves take effect immediately via hot-reload, no restart. (The English dashboard auto-hides Chinese-calendar elements — lunar date, solar terms, zodiac.)

**③ Set up the Kindle** (connected via USB, already jailbroken with USBNetwork/SSH enabled)

```bash
sh installers/kindle/install.sh
```

The script pushes the display scripts, writes the server address, adds autostart, and puts the dashboard on screen right away. After that, **just save config changes in the web page — you never touch the Kindle again.**

> **Done with it? One-command uninstall, Kindle fully back to normal**: `sh installers/kindle/uninstall.sh` stops the dashboard, removes autostart, deletes the pushed scripts, and restores the original UI — **the Kindle returns to its normal state and works as a regular e-reader again, with no leftovers**. Then `bash installers/macos/uninstall.sh` stops the Mac service.

## What is this

The Kindle acts as a thin client: it just periodically fetches one pre-rendered PNG and pushes it to the screen. Collection, aggregation, and rendering all happen on one always-on computer (Mac/NAS/Windows).

```
data sources → service on always-on computer (collect + Chromium render PNG) → Kindle fetches image every 20s
```

- Weather, reminders, AI usage, device monitoring (Win/Linux/Mac), a Home Assistant entity wall, and a 3D printer (the last two via Home Assistant)
- **Config-driven**: every IP / key / page / style is read from the web settings; nothing user-specific is hardcoded
- **Config = pages**: a page shows only if its data source is configured; unconfigured pages auto-hide
- **Honest degradation**: missing data shows a placeholder — never an error, never a blank screen; one failing source doesn't affect the others

## Screenshots

A few pages of the magazine-style `style_a` (default skin) — all rendered with **demo data**:

| ![Home](docs/img/style_a_home.png)<br>**Home** | ![AI usage](docs/img/style_a_ai.png)<br>**AI usage** |
|:---:|:---:|
| ![Devices](docs/img/style_a_device.png)<br>**Devices** | ![3D printer](docs/img/style_a_printer.png)<br>**3D printer** |

The same Home page in different built-in skins (**7 total**):

| ![terminal](docs/img/skin_terminal.png)<br>`terminal` | ![newspaper](docs/img/skin_newspaper.png)<br>`newspaper` | ![bento](docs/img/skin_bento.png)<br>`bento` |
|:---:|:---:|:---:|

> Shown upright in landscape; on the actual Kindle it's a rotated **portrait grayscale** image.

## Requirements

- An **always-on** computer: Mac, NAS (Docker), or Windows
- **Chrome or Chromium** for rendering (optional: the installer can auto-download a bundled chromium into the virtualenv without touching your system; on Windows, `playwright install chromium` does this)
- A **jailbroken** Kindle with **SSH enabled** (this project does not include jailbreak tools; the standard jailbreak toolchain MRPI already ships fbink)
- A **data-capable** USB cable (not a charge-only cable)

<details>
<summary><b>How to enable SSH on the Kindle</b> (one-time setup after jailbreak; skip if already done)</summary>

After jailbreaking, the Kindle will have a **KUAL** app (launcher). Open it:

**USB SSH (recommended for first-time setup — no WiFi needed):**
1. KUAL → **USBNetwork** → **Toggle USBNetwork** (`usbnet` status changes to `enabled`)
2. KUAL → USBNetwork → **Toggle SSH over USB only** (confirm `sshd for USB` shows `enabled`)
3. Connect the Kindle to your computer with a data cable — a new USB network adapter appears
4. On your computer: `ssh root@192.168.15.244` (password `mario`, the jailbreak default; use yours if you changed it)
5. After setting up the dashboard you can unplug — the Kindle fetches images over WiFi, no permanent USB connection needed

**WiFi SSH (convenient for remote access, but you need to know the Kindle's IP first):**
1. Make sure the Kindle is on the same WiFi as your computer
2. KUAL → USBNetwork → **Toggle SSH over WiFi** (confirm `sshd for WiFi` shows `enabled`)
3. Find the Kindle's IP: Home → Settings → Device Info → look for the WiFi IP (e.g. `192.168.5.36`)
4. On your computer: `ssh root@192.168.5.36` (same password)

> If you don't see USBNetwork in KUAL, the jailbreak is missing the USBNetwork hack — download `kindle-usbnet-hack` for your model from the MobileRead forums and install it.
</details>

## Quick start

### 1. Install the service

See "🚀 One-command deploy ①" above. To run manually (for debugging): `.venv/bin/python -m server.run` (macOS/Linux) or `.\.venv\Scripts\python -m server.run` (Windows).

- Config file: **stored outside the repo** at `~/.config/kindle-dashboard/config.yaml` (override with `KINDLE_CONFIG`) — so **upgrades / reinstalls / delete-and-reclone never lose your settings**; an old in-repo `config.yaml` is auto-migrated
- Logs: `data/*.log`, auto-rotated by the service (truncated to the last 1MB past 5MB) so long runs won't fill the disk
- **Access token**: auto-generated on first start, stored in `server.access_token` of `config.yaml`, to keep others on the same WiFi from snooping/tampering with the settings page. **Open the settings page via the token link**; Kindle image fetch, device reporting, and `/health` are exempt.
- **Online upgrade** (macOS): menu bar → "Check for updates"; if a new version exists, click "Upgrade" to auto `git pull` + restart (config lives outside the repo, so upgrades never touch your settings).

### 2. Configure via web

See "🚀 One-command deploy ②" above. Fill in by module:

- **Weather**: QWeather API Key + API Host + city (search by city name and pick — the code is matched automatically)
- **AI usage**: reads local ccusage directly; choose "enable" at install time and it's set up automatically. You can set **Claude / Codex price multipliers** (for reconciling with a relay provider — official price × multiplier)
- **Device monitoring**: add machines to monitor (local read / push agent / SSH pull), rename them, pick which metrics to show
- **Home Assistant**: address + long-lived access token (required for the printer / smart-home pages to appear)
- **Pages & styles**: choose a style (7 skins), choose your Kindle model (renders at native resolution), live preview on the right

### 3. Set up the Kindle

See "🚀 One-command deploy ③" above. Full commands (args optional):

```bash
sh installers/kindle/detect.sh [KINDLE_IP]                 # first confirm the Kindle is detected
sh installers/kindle/install.sh [KINDLE_IP] [SERVER_URL] [INTERVAL]
```

The Kindle starts showing the dashboard (**landscape**, top edge to the right). The installer asks for the **Kindle fetch interval** (default 20s).

> **SSH root password**: jailbreak packages often default to `mario`; use yours if you changed it (the script reminds you).
> **Server IP keeps changing?** On macOS this is usually Apple's "Private Wi-Fi Address" rotation — switch that option from "Rotating" to "Fixed" for the current network. On Windows, set a static IP or DHCP reservation for the always-on machine (see [docs/install.md](docs/install.md)).

## AI quota (Claude 5h / weekly)

The Claude rate-limit windows are collected via Claude Code's official **`statusLine`** hook — Claude Code pipes a JSON blob (containing `rate_limits.five_hour` / `seven_day`) into your status-line command on every refresh. The bundled script reads that and POSTs it to the dashboard at `/api/rate-limits`. This works on any OS Claude Code runs on, including Windows — no launchd or background daemon.

**Windows wiring** (the script is `installers/windows/quota/claude_statusline.py`):

1. Edit the push URL in `installers/windows/quota/quota.conf` if the dashboard isn't on `127.0.0.1:8585`.
2. Point your Claude Code status line at the script in `~/.claude/settings.json`:
   ```json
   "statusLine": {
     "type": "command",
     "command": "\"<repo>\\.venv\\Scripts\\python.exe\" \"<repo>\\installers\\windows\\quota\\claude_statusline.py\"",
     "refreshInterval": 180
   }
   ```
3. The status bar shows `Ctx · 5h · Wk` and pushes the quota to the dashboard (throttled by `KINDLE_QUOTA_PUSH_INTERVAL`).

> Already have your own status line? You don't have to replace it — copy the `>>> push quota` block from the script into your own.

> **Codex quota** and **Apple Reminders** remain macOS-only (Codex uses a non-public endpoint + a scheduled timer; Reminders reads Reminders.app via AppleScript). On Windows, use **Microsoft To Do** for reminders instead (built in, no API key).

## Uninstall (one command, fully restored)

You can back out anytime — the **Kindle is cleanly restored to its normal state** and works as a regular e-reader again, with no leftover scripts or autostart entries (this project only touches dashboard-related parts, never your jailbreak):

```bash
sh installers/kindle/uninstall.sh       # restore Kindle: stop dashboard, remove autostart, delete pushed scripts, restore UI
bash installers/macos/uninstall.sh      # stop the Mac service (add --purge to also delete venv/data for a full wipe)
```

> On Windows, stop the running `python -m server.run` process and remove any Task Scheduler entry you created. To undo the Claude status line, restore the `~/.claude/settings.json` backup written next to it (`settings.json.kindle-bak.<timestamp>`).

## NAS Docker deploy

Don't want to keep a Mac running 24/7? Run the dashboard service on a NAS (Docker) — the Mac only pushes data.

**On the NAS (once)**

```bash
git clone <repo-url> kindle-dashboard && cd kindle-dashboard
bash installers/nas/install.sh
```

The script builds the image, starts the container, waits for the health check, and prints the settings-page link plus Mac-side commands. The container ships with Chromium + CJK fonts + zombie reaping (tini), ready out of the box.

Config and data live in Docker volumes (`config` / `data`) — **rebuilding the container never loses them**.

**On the Mac (push data to the NAS)**

**No need to clone the repo on the Mac.** Replace `NAS_IP` with your NAS's LAN address (e.g. `192.168.5.138`); each command is one line:

```bash
# ① AI usage (ccusage): collect local Claude/Codex logs, push to NAS
#    Prerequisite: install ccusage first → npm install -g ccusage
curl -fsSL http://NAS_IP:8585/agent/install_ccusage.sh | sh -s -- http://NAS_IP:8585

# ② Reminders: read local Reminders.app, push to NAS (macOS only)
curl -fsSL http://NAS_IP:8585/agent/install_reminders.sh | sh -s -- http://NAS_IP:8585

# ③ AI quota (Claude/Codex 5h·weekly windows, macOS only)
curl -fsSL http://NAS_IP:8585/agent/install_quota.sh | sh -s -- http://NAS_IP:8585
```

Each command downloads a lightweight script from the NAS into `~/.kindle-dashboard/` and sets up a launchd timer — **survives Mac reboot automatically**. No Python venv, no config.yaml, no repo clone.

You can also open the NAS settings page — each data-source card shows the corresponding command with the NAS address pre-filled (just copy and paste).

To disable a specific push (replace the trailing argument with `uninstall`):
```bash
curl -fsSL http://NAS_IP:8585/agent/install_ccusage.sh | sh -s -- uninstall
curl -fsSL http://NAS_IP:8585/agent/install_reminders.sh | sh -s -- uninstall
curl -fsSL http://NAS_IP:8585/agent/install_quota.sh | sh -s -- uninstall
```

**Multiple Macs / devices**: just run the enable commands on each machine — devices are auto-identified by hostname. The dashboard service **sums all devices' data by date + model** (no overwriting, no max) so the AI page shows the combined total across all machines.

**How to confirm pushes are working**: open the NAS settings page in a browser — the corresponding module should show data; or run `curl http://NAS_IP:8585/health` and check if the `rendered` array includes the relevant pages.

**On the Kindle**

```bash
sh installers/kindle/install.sh KINDLE_IP http://NAS_IP:8585
```

Point the Kindle's image URL at the NAS (the second argument is the dashboard service address).

**Management**

```bash
cd installers/nas
docker compose logs -f           # view logs
docker compose restart           # restart (config preserved)
docker compose down              # stop
docker compose up -d --build     # rebuild (after code updates)
```

## Data sources

| Page | Source | Needs |
|---|---|---|
| Weather / Home | QWeather | API Key + API Host + city |
| Reminders | Apple Reminders (incl. iPhone via iCloud) | a Mac running the sync script |
| Reminders | Microsoft To Do | one Microsoft sign-in (no API key) |
| AI usage | ccusage (local read, no middleware) | a machine with ccusage (auto-installed) |
| AI quota | Claude / Codex 5h·weekly windows | Claude: any OS via statusLine; Codex: macOS only |
| Device monitoring | Win/Linux/Mac | local read / push agent / SSH pull |
| Smart home | Home Assistant entities | HA address + token, pick entities in web |
| 3D printer | Bambu Lab (via Home Assistant) | HA address + token |

See [docs/install.md](docs/install.md) (detailed steps + troubleshooting), [data contract](docs/data-contract.md).

## Styles & resolutions

Styles are decoupled as "data contract + style pack": all styles reference the same [data contract](docs/data-contract.md), switchable from a web dropdown with live preview. **7 skins** are built in (`style_a` magazine-style + `terminal`/`bento`/`blueprint`/`minimal`/`newspaper`/`gauge`), each covering every page. To author a new style, see [docs/style-authoring.md](docs/style-authoring.md).

**Multi-resolution**: pick your Kindle model in settings and it renders at native resolution (basic 6″ / Paperwhite / Oasis / Scribe…). Styles are designed against an 800×600 base canvas and vector-scaled at render time via Chrome's `--force-device-scale-factor` — fonts and lines stay sharp, with zero CSS changes. Just pick your model in settings — no manual configuration needed.

## Status & roadmap

✅ **P0 (Mac) core loop verified on real hardware** (Mac service install / web config & preview / one-command Kindle display / one-command rollback all run on real devices).
✅ **P1 (NAS Docker) implemented** — `docker compose up` one-command deploy with Chromium / CJK fonts / zombie reaping baked into the image; Mac data (ccusage / reminders / quota) pushed to NAS via scripts, multi-device daily totals summed automatically.
✅ **Windows fork** — render engine + Chrome detection + Claude quota statusLine run natively on Windows (verified rendering on real hardware). No one-command installer / tray app / launchd autostart yet.
🚧 Some macOS/Windows collection paths (push agent, SSH pull) await more real-device verification.
The full automated test suite (`python3 -m pytest tests/ -q`) covers config schema/loading/validation, the data contract/integration, real render-pipeline output, style scheduling, end-to-end Linux collection, all main-service APIs, the settings page with live preview, and NAS multi-device merge.

Roadmap: **P0 Mac ✅ → P1 NAS Docker ✅ → Windows fork ✅ → P2 style system → P3 extensions**.

## License

Open-sourced under the **MIT License**, see [LICENSE](LICENSE). Free to use, modify, and use commercially as long as the copyright notice is retained; the software is provided "as is", without warranty, and the author bears no liability.
