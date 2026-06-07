#!/bin/bash
# Kindle Dashboard —— 停用「AI 额度」上报(仅 macOS)。卸 Codex launchd 定时器。
# Claude 那半的 statusLine 不强行还原(可能是你自己的脚本),按提示自行处理。

LABEL="com.kindle-dashboard.codex-quota"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if command -v launchctl >/dev/null 2>&1; then
  launchctl unload "$PLIST" 2>/dev/null || true
fi
rm -f "$PLIST"
echo "✓ 已停用 Codex 额度采集(launchd 卸载)。"
echo
echo "Claude 额度(statusLine)如何撤:"
echo "  · 若当初是本工具自动写入的 → 编辑 ~/.claude/settings.json 删掉 statusLine 段,"
echo "    或恢复同目录的 settings.json.kindle-bak.* 备份;"
echo "  · 若是你把那段 POST 抄进了自己的 statusLine → 自行删掉那段即可。"
echo "  (停服务后看板 AI 页额度会停在最后一次的值,属正常降级,不报错。)"
