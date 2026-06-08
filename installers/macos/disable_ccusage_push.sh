#!/bin/bash
# Kindle Dashboard —— 停用 ccusage 推送

LABEL="com.kindle-dashboard.ccusage-push"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "✓ ccusage 推送已停用(launchd 定时器已移除)"
else
    echo "未找到 ccusage 推送定时器,可能已停用。"
fi
