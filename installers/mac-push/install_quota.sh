#!/bin/sh
# Kindle Dashboard —— 一键安装「AI 额度(Claude/Codex)推送」(macOS,独立,不需要 clone 仓库)。
# 由看板 NAS 服务在 /agent/install_quota.sh 下发;设置页给一行命令。
#
# 用法:
#   curl -fsSL http://<NAS>:8585/agent/install_quota.sh | sh -s -- http://<NAS>:8585
#   卸载: curl -fsSL http://<NAS>:8585/agent/install_quota.sh | sh -s -- uninstall
#
# 两件事:
#   1) Claude 额度:走 Claude Code 官方 statusLine(稳)。检测 ~/.claude/settings.json。
#   2) Codex 额度:装 launchd 定时器调 wham/usage(非公开接口)。
set -e

DIR="$HOME/.kindle-dashboard"
LABEL_CODEX="com.kindle-dashboard.codex-quota"
PLIST_CODEX="$HOME/Library/LaunchAgents/$LABEL_CODEX.plist"

uninstall() {
  echo "==> 卸载 AI 额度推送..."
  launchctl unload "$PLIST_CODEX" 2>/dev/null || true
  rm -f "$PLIST_CODEX"
  rm -f "$DIR/claude_statusline.py" "$DIR/codex_quota.py" "$DIR/sync_codex_quota.sh" "$DIR/quota.conf"
  echo "✓ 已卸载 Codex 额度定时器 + 删除脚本。"
  echo "  Claude statusLine 如需恢复:编辑 ~/.claude/settings.json 删掉 statusLine 行(或还原备份)。"
}

[ "$1" = "uninstall" ] && { uninstall; exit 0; }

URL="$1"
case "$URL" in
  http://*|https://*) : ;;
  *) echo "✗ 用法: curl -fsSL <NAS地址>/agent/install_quota.sh | sh -s -- <NAS地址>"; exit 1 ;;
esac
URL="$(printf '%s' "$URL" | sed 's#/*$##')"
RL_URL="$URL/api/rate-limits"

[ "$(uname -s)" = "Darwin" ] || { echo "✗ AI 额度推送只在 macOS 上可用(Claude Code + Codex CLI 场景)。"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "✗ 未找到 python3。"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "✗ 未找到 curl。"; exit 1; }

echo "==> 安装 AI 额度推送 → $URL..."
mkdir -p "$DIR/logs"

# 下载 Python 脚本
curl -fsSL "$URL/agent/claude_statusline.py" -o "$DIR/claude_statusline.py"
curl -fsSL "$URL/agent/codex_quota.py"       -o "$DIR/codex_quota.py"
chmod +x "$DIR/claude_statusline.py" "$DIR/codex_quota.py"

# 写 quota.conf(Claude statusLine 读这个)
cat > "$DIR/quota.conf" <<EOF
KINDLE_RATELIMIT_URL=$RL_URL
KINDLE_QUOTA_PUSH_INTERVAL=300
EOF

# ---------- 1. Claude:statusLine 集成 ----------
echo "== Claude 额度(走 Claude Code 官方 statusLine,稳)=="
SETTINGS="$HOME/.claude/settings.json"
if [ ! -f "$SETTINGS" ]; then
  echo "  未发现 ~/.claude/settings.json(此机可能没装 Claude Code)。"
  echo "  若在此机用 Claude Code:把 statusLine 指向 $DIR/claude_statusline.py 即可。"
elif python3 -c "import json,sys;sys.exit(0 if (json.load(open('$SETTINGS')) or {}).get('statusLine') else 1)" 2>/dev/null; then
  echo "  检测到你已自定义 statusLine,不覆盖。"
  echo "  要让它顺便上报 Claude 额度:把 $DIR/claude_statusline.py 里 '>>> 上报额度' 那段抄进你的脚本。"
else
  cp "$SETTINGS" "$SETTINGS.kindle-bak.$(date +%s)" 2>/dev/null || true
  if python3 - "$SETTINGS" "$DIR/claude_statusline.py" <<'PYEOF'
import json, sys
p, sl = sys.argv[1], sys.argv[2]
d = json.load(open(p)) or {}
d["statusLine"] = {"type": "command", "command": sl, "refreshInterval": 180}
json.dump(d, open(p, "w"), indent=2, ensure_ascii=False)
PYEOF
  then
    echo "  ✓ 已写入 statusLine(指向 $DIR/claude_statusline.py;原 settings.json 已备份)。"
  else
    echo "  ⚠ 写 settings.json 失败,跳过 Claude statusLine。"
  fi
fi

# ---------- 2. Codex:launchd 定时上报 ----------
echo "== Codex 额度(定时调 wham/usage;非公开接口,可能随官方变动失效)=="
[ -f "$HOME/.codex/auth.json" ] || echo "  ⚠ 没找到 ~/.codex/auth.json(没登录过 Codex CLI 的话 Codex 额度拿不到)。"

# 生成 sync 脚本
cat > "$DIR/sync_codex_quota.sh" <<'SYNC'
#!/bin/sh
PY="${KINDLE_PY:-python3}"
RAW=$("$PY" "$HOME/.kindle-dashboard/codex_quota.py" 2>/dev/null)
if ! printf '%s' "$RAW" | grep -q '"primary"'; then
    echo "$(date '+%F %T') Codex 额度获取失败:$RAW"
    exit 0
fi
PAYLOAD=$(printf '%s' "$RAW" | "$PY" -c "
import json, sys
d = json.load(sys.stdin)
p = d.get('primary', {}); s = d.get('secondary', {})
print(json.dumps({'source': 'codex', 'rate_limits': {
    'five_hour': {'used_percentage': p.get('usedPercent', 0), 'resets_at': p.get('resetsAt', 0)},
    'seven_day': {'used_percentage': s.get('usedPercent', 0), 'resets_at': s.get('resetsAt', 0)},
}}))
" 2>/dev/null)
if [ -n "$PAYLOAD" ]; then
    if curl -s -m 15 -X POST "$KINDLE_RATELIMIT_URL" -H "Content-Type: application/json" -d "$PAYLOAD" >/dev/null 2>&1; then
        echo "$(date '+%F %T') Codex 额度已推送 -> $KINDLE_RATELIMIT_URL"
    else
        echo "$(date '+%F %T') POST 失败 -> $KINDLE_RATELIMIT_URL"
    fi
fi
SYNC
chmod +x "$DIR/sync_codex_quota.sh"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_CODEX" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL_CODEX</string>
  <key>ProgramArguments</key>
  <array><string>/bin/sh</string><string>$DIR/sync_codex_quota.sh</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>KINDLE_RATELIMIT_URL</key><string>$RL_URL</string>
    <key>KINDLE_PY</key><string>python3</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartInterval</key><integer>600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DIR/logs/codex-quota.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/codex-quota.log</string>
</dict>
</plist>
EOF
launchctl unload "$PLIST_CODEX" 2>/dev/null || true
launchctl load -w "$PLIST_CODEX" 2>/dev/null && echo "  ✓ Codex 额度定时器已装(每 600 秒)。" \
  || echo "  ⚠ launchd 加载失败。"

echo "  立即采集一次 Codex 额度..."
KINDLE_RATELIMIT_URL="$RL_URL" KINDLE_PY="python3" sh "$DIR/sync_codex_quota.sh" || true

echo
echo "✓ AI 额度推送已安装。Claude 走 statusLine、Codex 走 launchd。"
echo "  卸载: curl -fsSL $URL/agent/install_quota.sh | sh -s -- uninstall"
