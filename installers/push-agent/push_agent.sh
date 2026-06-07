#!/bin/sh
# Kindle Dashboard 推送 agent —— 在【被监控机】上跑(Linux/macOS)。
# 循环:采集本机指标 → POST 到看板 /api/device-metrics → sleep 间隔。
# 配置从同目录 agent.env 读(URL/ID/INTERVAL/PLATFORM),由 install.sh 写好;也可用环境变量覆盖。
# 一般不用手调,install.sh 会装好并设开机自启。
DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$DIR/agent.env" ] && . "$DIR/agent.env"

URL="${URL:?缺少 URL(看板地址);请用 install.sh 安装}"
ID="${ID:-$(hostname 2>/dev/null || echo unknown)}"
INTERVAL="${INTERVAL:-30}"
PLATFORM="${PLATFORM:-linux}"
HOST="$(hostname 2>/dev/null || echo "$ID")"
COLLECTOR="$DIR/collect_${PLATFORM}.sh"

[ -f "$COLLECTOR" ] || { echo "缺少采集脚本:$COLLECTOR" >&2; exit 1; }

# JSON 字符串转义(ID/HOST 里的 " 和 \)
esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

while :; do
  M="$(COLLECT_INTERVAL=1 sh "$COLLECTOR" 2>/dev/null)"
  case "$M" in
    \{*\})   # 采到合法 JSON 才推
      BODY="{\"id\":\"$(esc "$ID")\",\"hostname\":\"$(esc "$HOST")\",\"metrics\":$M}"
      curl -s -m 10 -X POST "$URL/api/device-metrics" \
        -H "Content-Type: application/json" -d "$BODY" >/dev/null 2>&1 ;;
  esac
  sleep "$INTERVAL"
done
