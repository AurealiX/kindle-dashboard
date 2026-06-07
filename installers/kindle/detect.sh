#!/bin/sh
# 识别 Kindle:USB 物理接入 + SSH 可达。在主机(Mac/Linux)运行。
# 用法:sh installers/kindle/detect.sh [KINDLE_IP]
# 越狱 Kindle 开 USBNetwork 后,USB 网络默认 IP 通常是 192.168.15.244。
KINDLE_IP="${1:-192.168.15.244}"

echo "== 1) USB 物理接入 =="
case "$(uname)" in
  Darwin)
    if system_profiler SPUSBDataType 2>/dev/null | grep -iqE "kindle|amazon"; then
      echo "✓ 检测到 Kindle(Amazon USB 设备)"
      system_profiler SPUSBDataType 2>/dev/null | grep -iE "kindle|amazon|location id" | head -4
    else
      echo "✗ 未见 Kindle —— 确认数据线已连、Kindle 已解锁屏幕"
    fi ;;
  Linux)
    if lsusb 2>/dev/null | grep -iqE "amazon|1949:"; then
      echo "✓ 检测到 Kindle(Amazon vendor 1949)"
      lsusb 2>/dev/null | grep -iE "amazon|1949:"
    else
      echo "✗ 未见 Kindle"
    fi ;;
  *) echo "? 未知系统,跳过 USB 检测" ;;
esac

echo "== 2) SSH 可达($KINDLE_IP)=="
if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes root@"$KINDLE_IP" "echo ok" 2>/dev/null | grep -q ok; then
  echo "✓ 免密 SSH 可达 root@$KINDLE_IP(可直接安装)"
elif ping -c1 -W2 "$KINDLE_IP" >/dev/null 2>&1; then
  echo "✓ 网络可达 $KINDLE_IP(需密码,安装时会提示输入 Kindle root 密码)"
else
  echo "✗ 连不上 $KINDLE_IP。请确认:"
  echo "   ① Kindle 已越狱  ② 已开启 USBNetwork(SSH)  ③ 用支持数据传输的线"
fi
