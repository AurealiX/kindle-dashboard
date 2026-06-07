#!/bin/bash
# Kindle Dashboard —— 一键启用「AI 额度」上报(仅 macOS)。push 模式:设备采集 → POST 看板。
#
# 谁会调它:install.sh 选「是」时;或事后自己在终端跑。幂等,可重复运行。
#
# 做两件事:
#   1) Claude 额度:走 Claude Code 官方 statusLine —— 它把含 rate_limits 的 JSON 喂给状态栏命令。
#      检测 ~/.claude/settings.json:没配过 statusLine → 备份后写入指向本项目脚本;
#      已自定义 → 不覆盖,打印「把那段 POST 抄进你自己的 statusLine」的指引。
#   2) Codex 额度:装 launchd 定时器,每隔 ai_usage.codex_quota_interval 秒跑 codex_quota.py 上报。
#
# 间隔参数化:从 config 的 ai_usage.codex_quota_interval / claude_quota_interval 读(秒);改后重跑本脚本生效。
# 测试用:KINDLE_SKIP_AGENT=1 只做能在非 Mac 验证的部分,跳过 statusLine 写入与 launchd。

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="${KINDLE_CONFIG:-$REPO/config.yaml}"
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
QDIR="$REPO/installers/macos/quota"
LABEL="com.kindle-dashboard.codex-quota"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

die(){ echo "✗ $1"; exit 1; }
[ -f "$CONFIG" ] || die "没找到 config.yaml($CONFIG)。请先跑一次 install.sh。"
[ -n "$PY" ]     || die "未找到 python3。"

PORT=$("$PY" -c "import yaml;print((yaml.safe_load(open('$CONFIG')) or {}).get('server',{}).get('port',8585))" 2>/dev/null || echo 8585)
RL_URL="http://127.0.0.1:$PORT/api/rate-limits"
CX_INT=$("$PY" -c "import yaml;v=(yaml.safe_load(open('$CONFIG')) or {}).get('ai_usage',{}).get('codex_quota_interval',600);print(v if isinstance(v,int) and v>=60 else 600)" 2>/dev/null || echo 600)
CL_INT=$("$PY" -c "import yaml;v=(yaml.safe_load(open('$CONFIG')) or {}).get('ai_usage',{}).get('claude_quota_interval',300);print(v if isinstance(v,int) and v>=60 else 300)" 2>/dev/null || echo 300)
PROXY=$("$PY" -c "import yaml;print((yaml.safe_load(open('$CONFIG')) or {}).get('quota',{}).get('codex_proxy','') or '')" 2>/dev/null || echo "")

# Claude 脚本运行时读的地址/节流(statusLine 由 Claude Code 调,不走 launchd,没环境变量注入,靠这个 conf)
mkdir -p "$QDIR"
cat > "$QDIR/quota.conf" <<EOF
KINDLE_RATELIMIT_URL=$RL_URL
KINDLE_QUOTA_PUSH_INTERVAL=$CL_INT
EOF

# ---------- 1. Claude:statusLine 集成(已有则不覆盖,给指引)----------
echo "== Claude 额度(走 Claude Code 官方 statusLine,稳)=="
SETTINGS="$HOME/.claude/settings.json"
CLAUDE_SL="$QDIR/claude_statusline.py"
chmod +x "$CLAUDE_SL" 2>/dev/null || true
if [ "$KINDLE_SKIP_AGENT" = "1" ]; then
  echo "  (KINDLE_SKIP_AGENT=1:跳过 statusLine 配置)"
elif [ ! -f "$SETTINGS" ]; then
  echo "  未发现 ~/.claude/settings.json(此机可能没装 Claude Code 或没配过)。"
  echo "  若在此机用 Claude Code:把它 statusLine 指向 $CLAUDE_SL 即可上报 Claude 额度。"
elif "$PY" -c "import json,sys;sys.exit(0 if (json.load(open('$SETTINGS')) or {}).get('statusLine') else 1)" 2>/dev/null; then
  echo "  检测到你已自定义 statusLine,不覆盖。"
  echo "  要让它顺便上报 Claude 额度:把 $CLAUDE_SL 里 '# >>> 上报额度' 到 '# <<<' 那段抄进你的脚本即可"
  echo "  (它只读 stdin 的 rate_limits、POST 到 $RL_URL,与你的状态栏显示互不干扰)。"
else
  cp "$SETTINGS" "$SETTINGS.kindle-bak.$(date +%s)" 2>/dev/null || true
  if "$PY" - "$SETTINGS" "$CLAUDE_SL" <<'PYEOF'
import json, sys
p, sl = sys.argv[1], sys.argv[2]
d = json.load(open(p)) or {}
d["statusLine"] = {"type": "command", "command": sl, "refreshInterval": 180}
json.dump(d, open(p, "w"), indent=2, ensure_ascii=False)
PYEOF
  then
    echo "  ✓ 你还没配 statusLine,已写入(指向 $CLAUDE_SL;原 settings.json 已备份)。"
  else
    echo "  ⚠ 写 settings.json 失败,跳过 Claude statusLine(不影响 Codex)。"
  fi
fi

# ---------- 2. Codex:launchd 定时上报 ----------
echo "== Codex 额度(定时调 wham/usage 上报;非公开接口,可能随官方变动失效)=="
if [ "$KINDLE_SKIP_AGENT" = "1" ]; then
  echo "  (KINDLE_SKIP_AGENT=1:跳过 launchd)"; exit 0
fi
if ! command -v launchctl >/dev/null 2>&1; then
  echo "  ⚠ 当前不是 macOS,跳过 launchd。AI 额度上报只在 Mac 上有效。"; exit 0
fi
[ -f "$HOME/.codex/auth.json" ] || echo "  ⚠ 没找到 ~/.codex/auth.json —— 没登录过 Codex CLI 的话 Codex 额度拿不到(不影响 Claude)。"
SYNC="$QDIR/sync_codex_quota.sh"; chmod +x "$SYNC" 2>/dev/null || true
mkdir -p "$HOME/Library/LaunchAgents" "$REPO/data"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$SYNC</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>KINDLE_RATELIMIT_URL</key><string>$RL_URL</string>
    <key>KINDLE_PY</key><string>$PY</string>
    <key>CODEX_QUOTA_PROXY</key><string>$PROXY</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartInterval</key><integer>$CX_INT</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$REPO/data/codex-quota.log</string>
  <key>StandardErrorPath</key><string>$REPO/data/codex-quota.log</string>
</dict>
</plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
if launchctl load -w "$PLIST" 2>/dev/null; then
  echo "  ✓ Codex 额度采集已装(每 ${CX_INT} 秒上报一次)"
else
  echo "  ⚠ launchd 加载失败(不影响主服务 / Claude 额度)。"; exit 1
fi
echo "  立即采集一次 Codex 额度..."
KINDLE_RATELIMIT_URL="$RL_URL" KINDLE_PY="$PY" CODEX_QUOTA_PROXY="$PROXY" /bin/bash "$SYNC" || true
echo
echo "✓ AI 额度已启用。Claude 走 statusLine、Codex 走 launchd。看板 AI 页稍后即有额度数据。"
echo "  停用:bash installers/macos/disable_quota.sh"
