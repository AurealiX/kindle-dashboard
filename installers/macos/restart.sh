#!/bin/bash
# 重启 Kindle Dashboard 服务(改完代码后用),并自检确认起来了。
# 用法:bash installers/macos/restart.sh
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL="com.kindle-dashboard"
PLIST="$HOME/Library/LaunchAgents/com.kindle-dashboard.plist"

[ -f "$PLIST" ] || { echo "✗ 未找到服务,请先跑 install.sh"; exit 1; }

launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST" 2>/dev/null
launchctl start "$LABEL" 2>/dev/null

# 菜单栏是独立 agent;更新代码后也一并重启,让它加载新 menubar.py(装过才动)
MB_PLIST="$HOME/Library/LaunchAgents/com.kindle-dashboard.menubar.plist"
if [ -f "$MB_PLIST" ]; then
  launchctl unload "$MB_PLIST" 2>/dev/null
  launchctl load "$MB_PLIST" 2>/dev/null && echo "✓ 菜单栏已一并重启"
fi
echo "==> 服务已重启,自检中..."

PORT=$("$REPO/.venv/bin/python" -c "import yaml;print((yaml.safe_load(open('$REPO/config.yaml')) or {}).get('server',{}).get('port',8585))" 2>/dev/null || echo 8585)
for i in $(seq 1 15); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"status":"ok"'; then
    echo "✓ 服务正常(端口 $PORT)。刷新设置页即可:http://localhost:$PORT/setup"
    exit 0
  fi
  sleep 1
done
echo "⚠ 服务 15 秒内未响应,看日志:tail -25 $REPO/data/service.log"
exit 1
