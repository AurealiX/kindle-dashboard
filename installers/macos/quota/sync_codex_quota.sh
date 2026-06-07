#!/bin/bash
# Kindle Dashboard —— Codex 5h/周额度采集 + 推送(push)。
# 跑 codex_quota.py 拿额度 → 转成看板 /api/rate-limits 格式 → POST(source=codex)。
#
# 地址从 KINDLE_RATELIMIT_URL 读、代理从 CODEX_QUOTA_PROXY 读、python 从 KINDLE_PY 读
# (均由 enable_quota.sh 写进 launchd plist 注入);零硬编码。手动测试:
#   KINDLE_RATELIMIT_URL=http://127.0.0.1:8585/api/rate-limits bash sync_codex_quota.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="${KINDLE_PY:-python3}"
URL="${KINDLE_RATELIMIT_URL:-http://127.0.0.1:8585/api/rate-limits}"

RAW=$("$PY" "$SCRIPT_DIR/codex_quota.py" 2>/dev/null)
if ! printf '%s' "$RAW" | grep -q '"primary"'; then
    echo "$(date '+%F %T') Codex 额度获取失败:$RAW"
    exit 0
fi

PAYLOAD=$(printf '%s' "$RAW" | "$PY" -c "
import json, sys
d = json.load(sys.stdin)
p = d.get('primary', {}); s = d.get('secondary', {})
print(json.dumps({'source': 'codex', 'rate_limits': {
    'five_hour': {'used_percentage': p.get('usedPercent', 0), 'resets_at': p.get('resetsAt', 0)},
    'seven_day': {'used_percentage': s.get('usedPercent', 0), 'resets_at': s.get('resetsAt', 0)},
}}))
" 2>/dev/null)

if [ -n "$PAYLOAD" ]; then
    if curl -s -m 15 -X POST "$URL" -H "Content-Type: application/json" -d "$PAYLOAD" >/dev/null 2>&1; then
        echo "$(date '+%F %T') Codex 额度已推送 -> $URL"
    else
        echo "$(date '+%F %T') POST 失败 -> $URL"
    fi
fi
