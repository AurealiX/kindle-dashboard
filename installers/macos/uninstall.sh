#!/bin/bash
# Kindle Dashboard —— macOS 卸载(停服务、移除自启)。
# 默认保留 config.yaml 和 .venv;加 --purge 一并删除。
# 用法:bash installers/macos/uninstall.sh [--purge]
set -e

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PLIST_LABEL="com.kindle-dashboard"
PLIST="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

echo "==> 停止菜单栏程序..."
MB_PLIST="$HOME/Library/LaunchAgents/com.kindle-dashboard.menubar.plist"
MB_APP="$REPO/data/Kindle Dashboard Menu.app"
launchctl unload "$MB_PLIST" 2>/dev/null || true
rm -f "$MB_PLIST"
rm -rf "$MB_APP"

echo "==> 停止提醒事项同步..."
SYNC_PLIST="$HOME/Library/LaunchAgents/com.kindle-dashboard.reminders.plist"
launchctl unload "$SYNC_PLIST" 2>/dev/null || true
rm -f "$SYNC_PLIST"

echo "==> 停止并移除 launchd 服务..."
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "✓ 服务与菜单栏已停止,开机自启已移除"

CONFIG="${KINDLE_CONFIG:-$HOME/.config/kindle-dashboard/config.yaml}"
if [ "$1" = "--purge" ]; then
  echo "==> --purge:删除虚拟环境与运行数据..."
  rm -rf "$REPO/.venv" "$REPO/data"
  echo "✓ 已清理 .venv 和 data/"
  echo "  你的配置在仓库外($CONFIG),--purge 不动它;要连配置一起删:rm -rf \"$(dirname "$CONFIG")\""
else
  echo "  (保留 .venv、data/ 与配置;如需清理运行数据加 --purge)"
fi
echo "  配置文件位置:$CONFIG(在仓库外,升级/重装/删库重拉都不丢)"
echo "卸载完成。"
