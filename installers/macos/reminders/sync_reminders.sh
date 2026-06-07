#!/bin/bash
# Kindle Dashboard —— 苹果提醒事项采集 + 推送
# 读 Reminders.app(JXA),把提醒 POST 给看板服务的 /api/apple-sync。
#
# 推送地址从环境变量 KINDLE_SYNC_URL 读(由 launchd 注入,见 install.sh);
# 未设置时默认本机 8585。手动测试:
#   KINDLE_SYNC_URL=http://127.0.0.1:8585/api/apple-sync bash sync_reminders.sh
#
# 零硬编码:不写死任何 IP/端口,地址全部来自环境变量或默认本机。

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JXA_FILE="$SCRIPT_DIR/read_reminders.js"
URL="${KINDLE_SYNC_URL:-http://127.0.0.1:8585/api/apple-sync}"

JSON=$(osascript -l JavaScript "$JXA_FILE")

if [ $? -eq 0 ] && [ -n "$JSON" ]; then
    curl -s -m 15 -X POST "$URL" \
        -H "Content-Type: application/json" \
        -d "$JSON" > /dev/null 2>&1
    COUNT=$(echo "$JSON" | grep -o '"title"' | wc -l | tr -d ' ')
    echo "$(date '+%Y-%m-%d %H:%M:%S') 同步成功 - $COUNT 条 -> $URL"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') 读取提醒事项失败(可能未授予“提醒事项”权限,见安装文档)"
fi
