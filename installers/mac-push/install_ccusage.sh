#!/bin/sh
# Kindle Dashboard —— 一键安装「AI 用量(ccusage)推送」(独立,不需要 clone 仓库)。
# 由看板 NAS 服务在 /agent/install_ccusage.sh 下发;设置页给一行命令。
#
# 用法:
#   curl -fsSL http://<NAS>:8585/agent/install_ccusage.sh | sh -s -- http://<NAS>:8585 [间隔秒] [时区]
#   卸载: curl -fsSL http://<NAS>:8585/agent/install_ccusage.sh | sh -s -- uninstall
#
# 前提:本机已装 ccusage(npm i -g ccusage)。
# 装好后:每隔「间隔」秒采集本机 Claude/Codex 日志用量推给 NAS 看板,launchd 开机自启。
# 多台机器各推各的,看板自动按日汇总相加。
set -e

DIR="$HOME/.kindle-dashboard"
LABEL="com.kindle-dashboard.ccusage-push"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
CRON_TAG="# kindle-dash-ccusage"

stop_running() {
  if command -v pkill >/dev/null 2>&1; then
    pkill -f "$DIR/push_ccusage.sh" 2>/dev/null || true
  fi
}

uninstall() {
  echo "==> 卸载 ccusage 推送..."
  stop_running
  if [ "$(uname -s)" = "Darwin" ] && command -v launchctl >/dev/null 2>&1; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
  fi
  if command -v crontab >/dev/null 2>&1; then
    crontab -l 2>/dev/null | grep -v "$CRON_TAG" | crontab - 2>/dev/null || true
  fi
  rm -f "$DIR/push_ccusage.sh"
  echo "✓ 已卸载 ccusage 推送。"
}

[ "$1" = "uninstall" ] && { uninstall; exit 0; }

URL="$1"
INTERVAL="${2:-300}"
TZ_NAME="${3:-Asia/Shanghai}"
case "$URL" in
  http://*|https://*) : ;;
  *) echo "✗ 用法: curl -fsSL <NAS地址>/agent/install_ccusage.sh | sh -s -- <NAS地址> [间隔秒] [时区]"; exit 1 ;;
esac
case "$INTERVAL" in ''|*[!0-9]*) INTERVAL=300 ;; esac
[ "$INTERVAL" -lt 5 ] 2>/dev/null && INTERVAL=300
URL="$(printf '%s' "$URL" | sed 's#/*$##')"
DEVICE_ID="$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo unknown)"

command -v curl >/dev/null 2>&1 || { echo "✗ 未找到 curl。"; exit 1; }

# 找 ccusage
CCUSAGE=""
for c in "$HOME/.npm-global/bin/ccusage" /usr/local/bin/ccusage /opt/homebrew/bin/ccusage; do
  [ -x "$c" ] && CCUSAGE="$c" && break
done
[ -z "$CCUSAGE" ] && CCUSAGE="$(command -v ccusage 2>/dev/null || true)"
if [ -z "$CCUSAGE" ] || ! command -v "$CCUSAGE" >/dev/null 2>&1; then
  echo "✗ 未找到 ccusage。请先安装:"
  echo "  npm install -g ccusage"
  echo "  (需要 Node.js;装好后重跑本命令)"
  exit 1
fi
echo "  找到 ccusage: $CCUSAGE"

echo "==> 安装 ccusage 推送 → $URL (每 ${INTERVAL} 秒, 时区 $TZ_NAME, 设备 $DEVICE_ID)..."
mkdir -p "$DIR/logs"
stop_running

# 生成推送脚本
cat > "$DIR/push_ccusage.sh" <<PUSH
#!/bin/sh
export PATH="/usr/local/bin:/opt/homebrew/bin:\$PATH"
CCUSAGE=""
for c in "\$HOME/.npm-global/bin/ccusage" /usr/local/bin/ccusage /opt/homebrew/bin/ccusage; do
  [ -x "\$c" ] && CCUSAGE="\$c" && break
done
[ -z "\$CCUSAGE" ] && CCUSAGE="\$(command -v ccusage 2>/dev/null)"
[ -z "\$CCUSAGE" ] && { echo "\$(date '+%Y-%m-%d %H:%M:%S') ccusage 未找到"; exit 0; }
CC_JSON=\$("\$CCUSAGE" claude daily --json --timezone "\$KINDLE_TZ" 2>/dev/null)
CX_JSON=\$("\$CCUSAGE" codex daily --json --timezone "\$KINDLE_TZ" 2>/dev/null)
[ -z "\$CC_JSON" ] && CC_JSON='{"daily":[]}'
[ -z "\$CX_JSON" ] && CX_JSON='{"daily":[]}'
BODY="{\"id\":\"\$KINDLE_DEVICE_ID\",\"cc\":\$CC_JSON,\"codex\":\$CX_JSON}"
RESP=\$(curl -s -m 30 -X POST "\$KINDLE_DASH_URL/api/ccusage" -H "Content-Type: application/json" -d "\$BODY" 2>&1)
if echo "\$RESP" | grep -q '"status"'; then
  echo "\$(date '+%Y-%m-%d %H:%M:%S') 推送成功 (\$KINDLE_DEVICE_ID) -> \$KINDLE_DASH_URL/api/ccusage"
else
  echo "\$(date '+%Y-%m-%d %H:%M:%S') 推送失败: \$RESP"
fi
PUSH
chmod +x "$DIR/push_ccusage.sh"

PLATFORM="$(uname -s)"
if [ "$PLATFORM" = "Darwin" ] && command -v launchctl >/dev/null 2>&1; then
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/sh</string><string>$DIR/push_ccusage.sh</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>KINDLE_DASH_URL</key><string>$URL</string>
    <key>KINDLE_TZ</key><string>$TZ_NAME</string>
    <key>KINDLE_DEVICE_ID</key><string>$DEVICE_ID</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartInterval</key><integer>$INTERVAL</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DIR/logs/ccusage.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/ccusage.log</string>
</dict>
</plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load -w "$PLIST" 2>/dev/null && echo "✓ 已设 launchd 自启(每 ${INTERVAL} 秒推送)。" \
    || echo "⚠ launchd 加载失败。"
else
  # Linux: 后台跑 + cron
  ( setsid sh "$DIR/push_ccusage.sh" >"$DIR/logs/ccusage.log" 2>&1 & ) 2>/dev/null || true
  if command -v crontab >/dev/null 2>&1; then
    ( crontab -l 2>/dev/null | grep -v "$CRON_TAG"; \
      echo "*/$((INTERVAL/60>0?INTERVAL/60:1)) * * * * KINDLE_DASH_URL=$URL KINDLE_TZ=$TZ_NAME KINDLE_DEVICE_ID=$DEVICE_ID sh $DIR/push_ccusage.sh >>$DIR/logs/ccusage.log 2>&1 $CRON_TAG" ) | crontab - 2>/dev/null \
      && echo "✓ 已设 cron 定时推送。" || echo "⚠ 写 crontab 失败。"
  fi
fi

echo "==> 立即推送一次..."
KINDLE_DASH_URL="$URL" KINDLE_TZ="$TZ_NAME" KINDLE_DEVICE_ID="$DEVICE_ID" sh "$DIR/push_ccusage.sh"

echo
echo "✓ ccusage 推送已安装(设备: $DEVICE_ID)。"
echo "  卸载: curl -fsSL $URL/agent/install_ccusage.sh | sh -s -- uninstall"
