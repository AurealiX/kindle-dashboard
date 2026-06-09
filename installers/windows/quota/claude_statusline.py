#!/usr/bin/env python3
"""Claude Code status line: show context / 5h / weekly quota, and push the quota to the dashboard.

Claude Code pipes a JSON blob into this script via stdin (see the statusLine entry in settings.json);
its rate_limits.five_hour / seven_day fields are the 5-hour / weekly quota (used_percentage + resets_at).
This is the official Claude Code mechanism and is stable. This script also caches it locally and POSTs it
to the dashboard at /api/rate-limits (source=claude).

Zero hardcoding: the push URL / throttle are read from env vars KINDLE_RATELIMIT_URL /
KINDLE_QUOTA_PUSH_INTERVAL; failing that, from quota.conf in the same directory (written by the installer);
failing that, the local default.

-- Already have your own statusLine? You don't have to replace it with this script. Just copy the
   ">>> push quota" block below into your own script (it only needs rate_limits from stdin and is
   independent of whatever your status bar displays).
"""
import sys, json, time, os

R = '\033[0m'
D = '\033[2m'


def color(pct: int) -> str:
    if pct >= 80:
        return '\033[31m'
    if pct >= 50:
        return '\033[33m'
    return '\033[32m'


def fmt_min(secs_left: int) -> str:
    if secs_left <= 0:
        return 'now'
    h, m = divmod(secs_left // 60, 60)
    return f'{h}h{m:02d}m' if h else f'{m}m'


def fmt_hour(secs_left: int) -> str:
    if secs_left <= 0:
        return 'now'
    h = (secs_left + 1800) // 3600
    if h >= 24:
        d, rem = divmod(h, 24)
        return f'{d}d{rem}h' if rem else f'{d}d'
    return f'{h}h'


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f'{n/1_000_000:.1f}M'
    if n >= 1000:
        return f'{n/1000:.1f}k'
    return str(n)


def _conf():
    """Push URL + throttle seconds: env vars first, then quota.conf in the same dir, then local default."""
    url = os.environ.get("KINDLE_RATELIMIT_URL")
    interval = os.environ.get("KINDLE_QUOTA_PUSH_INTERVAL")
    if not url or not interval:
        try:
            confp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quota.conf")
            for line in open(confp):
                k, _, v = line.strip().partition("=")
                if k == "KINDLE_RATELIMIT_URL" and not url:
                    url = v
                elif k == "KINDLE_QUOTA_PUSH_INTERVAL" and not interval:
                    interval = v
        except Exception:
            pass
    try:
        interval = int(interval)
    except (TypeError, ValueError):
        interval = 300
    return url or "http://127.0.0.1:8585/api/rate-limits", interval


try:
    data = json.loads(sys.stdin.read() or '{}')
except Exception:
    print('statusline: parse error')
    sys.exit(0)

now = int(time.time())
cw = data.get('context_window') or {}
rl = data.get('rate_limits') or {}
five = rl.get('five_hour') or {}
week = rl.get('seven_day') or {}

# >>> push quota (copy this block into your own statusLine to make it report Claude quota too)
if five or week:
    try:
        import subprocess
        url, push_interval = _conf()
        cache_data = {"timestamp": now, "rate_limits": rl}
        # local cache (optional, handy for debugging)
        try:
            with open(os.path.expanduser("~/.claude/rate-limits.json"), "w") as f:
                json.dump(cache_data, f)
        except Exception:
            pass
        # throttle by push_interval so we don't hit the server on every refresh
        marker = os.path.expanduser("~/.claude/.kindle-quota-pushed")
        should_push = True
        try:
            if os.path.exists(marker) and (now - int(os.path.getmtime(marker))) < push_interval:
                should_push = False
        except Exception:
            pass
        if should_push:
            open(marker, "w").close()
            subprocess.Popen(
                ["curl", "-s", "-m", "10", "-X", "POST", url,
                 "-H", "Content-Type: application/json",
                 "-d", json.dumps({"source": "claude", "rate_limits": rl})],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
# <<< push quota

# ---- status bar display ----
ctx_pct = int(cw.get('used_percentage') or 0)
ctx_used = (cw.get('total_input_tokens') or 0) + (cw.get('total_output_tokens') or 0)
ctx_size = cw.get('context_window_size') or 0
ctx_tag = fmt_tokens(ctx_used) + (f'/{fmt_tokens(ctx_size)}' if ctx_size else '')

parts = [f'{D}Ctx{R} {color(ctx_pct)}{ctx_pct}%{R} {D}({ctx_tag}){R}']
if five:
    p = int(five.get('used_percentage') or 0)
    parts.append(f'{D}5h{R} {color(p)}{p}%{R} {D}↻{R}{fmt_min((five.get("resets_at") or 0) - now)}')
else:
    parts.append(f'{D}5h ?{R}')
if week:
    p = int(week.get('used_percentage') or 0)
    parts.append(f'{D}Wk{R} {color(p)}{p}%{R} {D}↻{R}{fmt_hour((week.get("resets_at") or 0) - now)}')
else:
    parts.append(f'{D}Wk ?{R}')

print(' · '.join(parts))
