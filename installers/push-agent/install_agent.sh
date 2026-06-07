#!/bin/sh
# Kindle Dashboard 推送 agent —— 一键安装(在【被监控机】上运行,Linux/macOS)。
# 由看板服务在 /agent/install.sh 提供;在设置页复制带地址的整行命令到目标机运行即可。
#
# 用法:
#   curl -fsSL http://<看板IP>:<端口>/agent/install.sh | sh -s -- http://<看板IP>:<端口> [间隔秒] [标识]
#   卸载:curl -fsSL http://<看板IP>:<端口>/agent/install.sh | sh -s -- uninstall
#
# 装好后:agent 每隔「间隔」秒采集本机指标推给看板;Linux 设 @reboot 自启,macOS 设 launchd 自启。
# 目标机在看板设置页「设备监控」会自动出现(以 hostname 为标识),可在那里改名、选指标。
set -e

AGENT_DIR="$HOME/.kindle-dash-agent"
LABEL="com.kindle-dashboard.agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
CRON_TAG="# kindle-dash-agent"

stop_running() {
  # 停掉正在跑的 loop(不依赖 pkill 是否存在)
  if command -v pkill >/dev/null 2>&1; then
    pkill -f "$AGENT_DIR/push_agent.sh" 2>/dev/null || true
  else
    for p in $(ps ax 2>/dev/null | grep "$AGENT_DIR/push_agent.sh" | grep -v grep | awk '{print $1}'); do
      kill "$p" 2>/dev/null || true
    done
  fi
}

uninstall() {
  echo "==> 卸载推送 agent..."
  stop_running
  if [ "$(uname -s)" = "Darwin" ] && command -v launchctl >/dev/null 2>&1; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
  fi
  if command -v crontab >/dev/null 2>&1; then
    crontab -l 2>/dev/null | grep -v "$CRON_TAG" | crontab - 2>/dev/null || true
  fi
  rm -rf "$AGENT_DIR"
  echo "✓ 已卸载:停止上报、清开机自启、删除 $AGENT_DIR。看板设置页那台设备会随之不再更新。"
}

[ "$1" = "uninstall" ] && { uninstall; exit 0; }

URL="$1"
INTERVAL="${2:-30}"
ID="${3:-$(hostname 2>/dev/null || echo unknown)}"
case "$URL" in
  http://*|https://*) : ;;
  *) echo "✗ 用法:curl -fsSL <看板地址>/agent/install.sh | sh -s -- <看板地址> [间隔秒] [标识]"; exit 1 ;;
esac
case "$INTERVAL" in ''|*[!0-9]*) INTERVAL=30 ;; esac
[ "$INTERVAL" -lt 5 ] 2>/dev/null && INTERVAL=30
URL="$(printf '%s' "$URL" | sed 's#/*$##')"   # 去掉末尾斜杠

case "$(uname -s)" in
  Linux)  PLATFORM=linux ;;
  Darwin) PLATFORM=macos ;;
  *) echo "✗ 不支持的系统:$(uname -s)。Windows 请用设置页提供的 PowerShell 命令。"; exit 1 ;;
esac

command -v curl >/dev/null 2>&1 || { echo "✗ 需要 curl,请先安装(NAS 一般自带;或用 wget 改装)"; exit 1; }

echo "==> 安装到 $AGENT_DIR(系统 =$PLATFORM,间隔 =${INTERVAL}s,标识 =$ID)..."
stop_running
mkdir -p "$AGENT_DIR"
curl -fsSL "$URL/agent/push_agent.sh"          -o "$AGENT_DIR/push_agent.sh"
curl -fsSL "$URL/agent/collect_${PLATFORM}.sh" -o "$AGENT_DIR/collect_${PLATFORM}.sh"
chmod +x "$AGENT_DIR/push_agent.sh" "$AGENT_DIR/collect_${PLATFORM}.sh"
cat > "$AGENT_DIR/agent.env" <<EOF
URL=$URL
ID=$ID
INTERVAL=$INTERVAL
PLATFORM=$PLATFORM
EOF

if [ "$PLATFORM" = "macos" ]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/sh</string><string>$AGENT_DIR/push_agent.sh</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$AGENT_DIR/agent.log</string>
  <key>StandardErrorPath</key><string>$AGENT_DIR/agent.log</string>
</dict>
</plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load -w "$PLIST" 2>/dev/null && echo "✓ 已设 launchd 自启(登录即跑、退出自动重启)。" \
    || echo "⚠ launchd 加载失败,agent 仍会被下面手动启动,但开机自启没设上。"
else
  # Linux:后台起 + @reboot 自启(cron 最通用;NAS 一般都有)
  ( setsid sh "$AGENT_DIR/push_agent.sh" >"$AGENT_DIR/agent.log" 2>&1 & ) 2>/dev/null \
    || ( nohup sh "$AGENT_DIR/push_agent.sh" >"$AGENT_DIR/agent.log" 2>&1 & )
  if command -v crontab >/dev/null 2>&1; then
    ( crontab -l 2>/dev/null | grep -v "$CRON_TAG"; \
      echo "@reboot sh $AGENT_DIR/push_agent.sh >$AGENT_DIR/agent.log 2>&1 $CRON_TAG" ) | crontab - 2>/dev/null \
      && echo "✓ 已设 @reboot 开机自启。" \
      || echo "⚠ 写 crontab 失败,开机自启没设上(agent 已在跑;重启后重跑本命令即可)。"
  else
    echo "⚠ 没有 crontab,开机自启没设上(agent 已在跑;重启后重跑本命令即可)。"
  fi
fi

echo "✓ 推送 agent 已启动,每 ${INTERVAL} 秒上报一次。"
echo "  回看板设置页「设备监控」→ 这台机器(标识 $ID)会自动出现,可改名、选要显示的指标。"
echo "  卸载:curl -fsSL $URL/agent/install.sh | sh -s -- uninstall"
