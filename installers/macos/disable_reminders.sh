#!/bin/bash
# Kindle Dashboard —— 一键停用「Mac/iPhone 提醒事项同步」(仅 macOS)
# 配置 reminders.enabled=false + 卸载 launchd agent。看板其余部分不受影响。
# 测试用:KINDLE_SKIP_AGENT=1 只改配置、跳过 launchd。

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="${KINDLE_CONFIG:-$REPO/config.yaml}"
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
SYNC_LABEL="com.kindle-dashboard.reminders"
SYNC_PLIST="$HOME/Library/LaunchAgents/$SYNC_LABEL.plist"

die(){ echo "✗ $1"; exit 1; }

[ -f "$CONFIG" ] || die "没找到 config.yaml($CONFIG)。"
[ -n "$PY" ] || die "未找到 python3。"

# 1) 配置停用
"$PY" - "$CONFIG" <<'PYEOF'
import sys, yaml
p = sys.argv[1]
c = yaml.safe_load(open(p, encoding="utf-8")) or {}
c.setdefault("reminders", {})["enabled"] = False
yaml.safe_dump(c, open(p, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
PYEOF
[ $? -eq 0 ] || die "写配置失败。"
echo "✓ 已在配置中停用提醒事项"

if [ "$KINDLE_SKIP_AGENT" = "1" ]; then
  echo "(KINDLE_SKIP_AGENT=1:跳过 launchd 卸载)"; exit 0
fi
command -v launchctl >/dev/null 2>&1 || { echo "⚠ 非 macOS,无 launchd 可卸。"; exit 0; }

# 2) 卸载 launchd agent
if [ -f "$SYNC_PLIST" ]; then
  launchctl unload "$SYNC_PLIST" 2>/dev/null || true
  rm -f "$SYNC_PLIST"
  echo "✓ 提醒事项同步 agent 已移除"
else
  echo "ℹ 没有已安装的同步 agent,无需移除"
fi
