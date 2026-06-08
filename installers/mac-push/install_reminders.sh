#!/bin/sh
# Kindle Dashboard —— 一键安装「提醒事项推送」(macOS,独立,不需要 clone 仓库)。
# 由看板 NAS 服务在 /agent/install_reminders.sh 下发;设置页给一行命令。
#
# 用法:
#   curl -fsSL http://<NAS>:8585/agent/install_reminders.sh | sh -s -- http://<NAS>:8585 [间隔秒]
#   卸载: curl -fsSL http://<NAS>:8585/agent/install_reminders.sh | sh -s -- uninstall
#
# 装好后:每隔「间隔」秒读 Mac 上的 Reminders.app 推给 NAS 看板,launchd 开机自启。
set -e

DIR="$HOME/.kindle-dashboard"
LABEL="com.kindle-dashboard.reminders"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

uninstall() {
  echo "==> 卸载提醒事项推送..."
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  rm -f "$DIR/read_reminders.js" "$DIR/sync_reminders.sh"
  echo "✓ 已卸载提醒事项推送。"
}

[ "$1" = "uninstall" ] && { uninstall; exit 0; }

URL="$1"
INTERVAL="${2:-300}"
case "$URL" in
  http://*|https://*) : ;;
  *) echo "✗ 用法: curl -fsSL <NAS地址>/agent/install_reminders.sh | sh -s -- <NAS地址> [间隔秒]"; exit 1 ;;
esac
case "$INTERVAL" in ''|*[!0-9]*) INTERVAL=300 ;; esac
[ "$INTERVAL" -lt 5 ] 2>/dev/null && INTERVAL=300
URL="$(printf '%s' "$URL" | sed 's#/*$##')"

[ "$(uname -s)" = "Darwin" ] || { echo "✗ 提醒事项推送只在 macOS 上可用(需要 osascript 读 Reminders.app)。"; exit 1; }
command -v osascript >/dev/null 2>&1 || { echo "✗ 未找到 osascript。"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "✗ 未找到 curl。"; exit 1; }

echo "==> 安装提醒事项推送 → $URL (每 ${INTERVAL} 秒)..."
mkdir -p "$DIR/logs"

# 下载 JXA 读提醒脚本
curl -fsSL "$URL/agent/read_reminders.js" -o "$DIR/read_reminders.js"

# 生成 sync 脚本
cat > "$DIR/sync_reminders.sh" <<'SYNC'
#!/bin/sh
JXA_FILE="$HOME/.kindle-dashboard/read_reminders.js"
JSON=$(osascript -l JavaScript "$JXA_FILE")
if [ $? -eq 0 ] && [ -n "$JSON" ]; then
    curl -s -m 15 -X POST "$KINDLE_SYNC_URL" \
        -H "Content-Type: application/json" \
        -d "$JSON" > /dev/null 2>&1
    COUNT=$(echo "$JSON" | grep -o '"title"' | wc -l | tr -d ' ')
    echo "$(date '+%Y-%m-%d %H:%M:%S') 同步成功 - $COUNT 条 -> $KINDLE_SYNC_URL"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') 读取提醒事项失败(可能未授予"提醒事项"权限)"
fi
SYNC
chmod +x "$DIR/sync_reminders.sh"

# 装 launchd
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/sh</string><string>$DIR/sync_reminders.sh</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>KINDLE_SYNC_URL</key><string>$URL/api/apple-sync</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartInterval</key><integer>$INTERVAL</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DIR/logs/reminders.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/reminders.log</string>
</dict>
</plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST" 2>/dev/null && echo "✓ 已设 launchd 自启(每 ${INTERVAL} 秒同步)。" \
  || echo "⚠ launchd 加载失败。"

# 前台跑一次触发 macOS 授权弹窗
echo "==> 立即同步一次 —— macOS 会弹「允许访问提醒事项」,请点【允许】..."
KINDLE_SYNC_URL="$URL/api/apple-sync" sh "$DIR/sync_reminders.sh"

echo
echo "✓ 提醒事项推送已安装。"
echo "  若没弹窗或误点了拒绝:系统设置 → 隐私与安全性 → 提醒事项,勾选 终端/osascript。"
echo "  卸载: curl -fsSL $URL/agent/install_reminders.sh | sh -s -- uninstall"
