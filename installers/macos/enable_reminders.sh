#!/bin/bash
# Kindle Dashboard —— 一键启用「Mac/iPhone 提醒事项同步」(仅 macOS)
#
# 谁会调它:
#   1) install.sh 里用户选「是」时自动调用;
#   2) 用户当初没选、后来想加 —— 在设置页复制这行命令,在 Mac 终端自己运行即可。
#
# 做三件事:
#   1) 配置 reminders.enabled=true
#   2) 装 launchd 同步 agent(每 5 分钟读 Reminders.app 推给看板)
#   3) 前台跑一次,触发 macOS「允许访问提醒事项」授权弹窗(后台 launchd 弹不出来,前台终端能弹)
# 幂等:可重复运行。
# 测试用:KINDLE_SKIP_AGENT=1 只改配置、跳过 launchd 与授权(供 CI/非 Mac 验证)。

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="${KINDLE_CONFIG:-$HOME/.config/kindle-dashboard/config.yaml}"
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
SYNC_LABEL="com.kindle-dashboard.reminders"
SYNC_PLIST="$HOME/Library/LaunchAgents/$SYNC_LABEL.plist"
SYNC_SH="$REPO/installers/macos/reminders/sync_reminders.sh"

die(){ echo "✗ $1"; exit 1; }

[ -f "$CONFIG" ] || die "没找到 config.yaml($CONFIG)。请先在项目目录跑一次安装(install.sh)。"
[ -n "$PY" ] || die "未找到 python3。"

# 1) 配置启用
"$PY" - "$CONFIG" <<'PYEOF'
import sys, yaml
p = sys.argv[1]
c = yaml.safe_load(open(p, encoding="utf-8")) or {}
c.setdefault("reminders", {})["enabled"] = True
yaml.safe_dump(c, open(p, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
PYEOF
[ $? -eq 0 ] || die "写配置失败。"
echo "✓ 已在配置中启用提醒事项"

# 测试 / 非 Mac:到此为止
if [ "$KINDLE_SKIP_AGENT" = "1" ]; then
  echo "(KINDLE_SKIP_AGENT=1:跳过 launchd 安装与授权)"; exit 0
fi
if ! command -v launchctl >/dev/null 2>&1; then
  echo "⚠ 当前不是 macOS,跳过 launchd 安装。提醒事项同步只在 Mac 上有效。"; exit 0
fi

PORT=$("$PY" -c "import yaml;print((yaml.safe_load(open('$CONFIG')) or {}).get('server',{}).get('port',8585))" 2>/dev/null || echo 8585)
# 提醒同步间隔(秒):从配置 intervals.reminders 读,默认 300。它是 launchd 定时器,改后需重跑本脚本生效。
REM_INTERVAL=$("$PY" -c "import yaml;v=(yaml.safe_load(open('$CONFIG')) or {}).get('reminders',{}).get('interval',300);print(v if isinstance(v,int) and v>=5 else 300)" 2>/dev/null || echo 300)
[ -f "$SYNC_SH" ] || die "缺少同步脚本:$SYNC_SH"
chmod +x "$SYNC_SH"

# 2) 装 launchd agent(注入推送地址 + 配置路径)
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$SYNC_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$SYNC_LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$SYNC_SH</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>KINDLE_SYNC_URL</key><string>http://127.0.0.1:$PORT/api/apple-sync</string>
    <key>KINDLE_CONFIG</key><string>$CONFIG</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartInterval</key><integer>$REM_INTERVAL</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$REPO/data/reminders.log</string>
  <key>StandardErrorPath</key><string>$REPO/data/reminders.log</string>
</dict>
</plist>
EOF
launchctl unload "$SYNC_PLIST" 2>/dev/null || true
if launchctl load -w "$SYNC_PLIST" 2>/dev/null; then
  echo "✓ 提醒事项同步已安装(每 ${REM_INTERVAL} 秒自动同步)"
else
  echo "⚠ launchd 加载失败(不影响看板主服务)。"; exit 1
fi

# 3) 前台跑一次触发授权弹窗
echo "==> 立即同步一次 —— macOS 会弹「允许访问提醒事项」,请点【允许】..."
KINDLE_SYNC_URL="http://127.0.0.1:$PORT/api/apple-sync" KINDLE_CONFIG="$CONFIG" /bin/bash "$SYNC_SH"
echo
echo "✓ 完成。若没弹窗或误点了拒绝:系统设置 → 隐私与安全性 → 提醒事项,勾选 终端/osascript,再重跑本命令。"
