#!/bin/sh
# Kindle 一键卸载/还原:停看板、移除自启、删脚本、恢复系统界面 —— 像没装过。
# 在主机(Mac/Linux)运行。用法:sh installers/kindle/uninstall.sh [KINDLE_IP]
KINDLE_IP="${1:-192.168.15.244}"
SSHOPT="-o StrictHostKeyChecking=no"

# USB 模式:与 install.sh 对称,自动给本机 USB 网卡配同网段 IP,实现"插 USB 一条命令卸载"。
# (逻辑与 installers/kindle/install.sh 的 ensure_usb_route 保持一致,改一处记得同步另一处)
ensure_usb_route() {
  [ "$KINDLE_IP" = "192.168.15.244" ] || return 0          # 仅 USBNetwork 标准地址才需要
  ping -c1 -t2 "$KINDLE_IP" >/dev/null 2>&1 && return 0     # 已通则跳过(幂等)
  echo "==> USB 网络未通,自动配置本机 USB 接口(等待接口就绪,最多 ~12 秒)..."
  case "$(uname)" in
    Darwin)
      n=0
      while [ $n -lt 6 ]; do
        for ifc in $(ifconfig -l 2>/dev/null | tr ' ' '\n' | grep '^en'); do
          if ifconfig "$ifc" 2>/dev/null | grep -q "inet 169.254"; then
            echo "   检测到 Kindle USB 接口 $ifc,配 192.168.15.201(可能需 sudo 密码)"
            echo "   (仅给这块 Kindle USB 网卡临时配地址,不影响你的 WiFi/上网;拔线或重启即自动恢复,无需手动还原)"
            sudo ifconfig "$ifc" 192.168.15.201 255.255.255.0 || true
            sleep 1
            ping -c1 -t2 "$KINDLE_IP" >/dev/null 2>&1 && { echo "   ✓ USB 网络已通"; return 0; }
          fi
        done
        n=$((n + 1)); sleep 2
      done ;;
    *) echo "   (非 macOS,请手动把 USB 网络接口配为 192.168.15.201/24)" ;;
  esac
  return 1
}
ensure_usb_route || echo "⚠ USB 网络仍未通;若改用 WiFi:uninstall.sh <KindleWiFiIP>"

echo "提示:接下来可能要求输入 Kindle 的 root 密码(越狱默认 mario)。"
echo "==> 还原 Kindle($KINDLE_IP)..."
ssh $SSHOPT root@"$KINDLE_IP" "
  [ -f /mnt/us/stop.sh ] && sh /mnt/us/stop.sh
  /usr/sbin/mntroot rw 2>/dev/null || true
  grep -v '/mnt/us/start.sh' /etc/crontab/root > /tmp/cr.tmp 2>/dev/null && mv /tmp/cr.tmp /etc/crontab/root
  /usr/sbin/mntroot ro 2>/dev/null || true
  rm -f /mnt/us/start.sh /mnt/us/stop.sh /mnt/us/dashboard.conf \
        /mnt/us/frame.png /mnt/us/frame_new.png /mnt/us/dashboard.pid
  /sbin/initctl start framework 2>/dev/null || true
  /sbin/initctl start pmond 2>/dev/null || true
  echo cleaned
" || { echo "✗ 无法 SSH 到 Kindle"; exit 1; }

echo "✓ 已还原:停看板、移除开机自启、删除脚本与图片、恢复界面。"
echo "  建议重启 Kindle 彻底恢复。"
