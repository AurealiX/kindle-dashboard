#!/bin/sh
# Kindle 一键配置:推送 start/stop 脚本、写服务地址、装开机自启、启动显示。
# 在主机(Mac/Linux)运行。Kindle 需已越狱 + 已开 USBNetwork(SSH)。
# 用法:sh installers/kindle/install.sh [KINDLE_IP] [SERVER_URL] [INTERVAL]
#   KINDLE_IP   默认 192.168.15.244(USBNetwork)
#   SERVER_URL  默认自动探测本机 IP:8585
#   INTERVAL    Kindle 拉图刷新间隔(秒);不给则交互询问,非交互默认 20
set -e
KDIR="$(cd "$(dirname "$0")" && pwd)"
KINDLE_IP="${1:-192.168.15.244}"
SERVER_URL="$2"
INTERVAL="$3"

# 自动探测服务地址(本机局域网 IP)
if [ -z "$SERVER_URL" ]; then
  case "$(uname)" in
    Darwin) IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null) ;;
    *)      IP=$(hostname -I 2>/dev/null | awk '{print $1}') ;;
  esac
  SERVER_URL="http://${IP:-127.0.0.1}:8585"
fi
echo "Kindle: $KINDLE_IP    服务地址: $SERVER_URL"

# Kindle 拉图刷新间隔(秒):第三参数优先,否则交互询问,非 tty 默认 20。
# 注意:这是 Kindle 端"多久拉一张新图"(写进 dashboard.conf,刷机时定,网页改不了);
#       与服务端"页面轮播间隔"(page_interval,网页可配)是两回事。
ask_interval() {
  if [ -n "$INTERVAL" ]; then
    if echo "$INTERVAL" | grep -q '^[0-9][0-9]*$' && [ "$INTERVAL" -ge 5 ]; then return; fi
    echo "  (刷新间隔参数无效,改用默认 20)"; INTERVAL=20; return
  fi
  if [ -t 0 ]; then
    echo "==> Kindle 多久拉一次新图?越短越实时、越费电。常用 10/20/30/60,回车默认 20。"
    printf "    刷新间隔(秒) [20]: "
    read ans 2>/dev/null || ans=""
    if echo "$ans" | grep -q '^[0-9][0-9]*$' && [ "$ans" -ge 5 ]; then
      INTERVAL="$ans"
    else
      [ -n "$ans" ] && echo "    (输入无效,用默认 20)"
      INTERVAL=20
    fi
  else
    INTERVAL=20
  fi
}
ask_interval
echo "   刷新间隔:${INTERVAL}s"

# Mac 局域网 IP 会随 DHCP 变 → 写一个备用 .local(mDNS)地址,主地址(IP)失效时 Kindle 端自动切。
# Kindle busybox 不一定能解析 .local(装完会实测告诉你);解析不了就需在路由器给 Mac 绑定静态 IP。
SERVER_URL_ALT=""
if [ "$(uname)" = "Darwin" ]; then
  lh=$(scutil --get LocalHostName 2>/dev/null)
  port=$(echo "$SERVER_URL" | sed -n 's#.*:\([0-9][0-9]*\)$#\1#p'); [ -z "$port" ] && port=8585
  if [ -n "$lh" ]; then
    cand="http://${lh}.local:${port}"
    [ "$cand" != "$SERVER_URL" ] && SERVER_URL_ALT="$cand"
  fi
fi
[ -n "$SERVER_URL_ALT" ] && echo "   备用地址(IP 变兜底):$SERVER_URL_ALT"

# USB 模式:自动给本机 USB 网卡配同网段 IP,最终用户无需手动 ifconfig(真·一键)
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
ensure_usb_route || echo "⚠ USB 网络仍未通;若改用 WiFi:install.sh <KindleWiFiIP> http://<MacIP>:8585"

# 复用 SSH 连接,只输一次密码
CP="/tmp/kindle-ctl-%r@%h:%p"
SSHOPT="-o StrictHostKeyChecking=no -o ControlMaster=auto -o ControlPath=$CP -o ControlPersist=120"
echo "提示:接下来会要求输入 Kindle 的 root 密码(越狱后的 SSH 密码)。"
echo "      越狱包常见默认密码是 mario;若你改过,请用你设的密码。"
ssh $SSHOPT root@"$KINDLE_IP" "echo connected" || { echo "✗ 无法 SSH 到 Kindle,先跑 detect.sh 排查"; exit 1; }

echo "==> 备份旧版(若有)..."
ssh $SSHOPT root@"$KINDLE_IP" "
  if [ -f /mnt/us/start.sh ] || [ -f /mnt/us/stop.sh ]; then
    mkdir -p /mnt/us/kindle-dash-backup
    cp /mnt/us/start.sh /mnt/us/kindle-dash-backup/ 2>/dev/null
    cp /mnt/us/stop.sh  /mnt/us/kindle-dash-backup/ 2>/dev/null
    cp /etc/crontab/root /mnt/us/kindle-dash-backup/crontab.root 2>/dev/null
    echo '  ✓ 旧 start.sh/stop.sh/crontab 已备份到 /mnt/us/kindle-dash-backup/'
  else echo '  (无旧版,跳过)'; fi
"

echo "==> 推送脚本..."
scp $SSHOPT "$KDIR/start.sh" "$KDIR/stop.sh" root@"$KINDLE_IP":/mnt/us/

echo "==> 写配置、装自启、启动..."
ssh $SSHOPT root@"$KINDLE_IP" "
  echo 'SERVER_URL=$SERVER_URL' > /mnt/us/dashboard.conf
  echo 'SERVER_URL_ALT=$SERVER_URL_ALT' >> /mnt/us/dashboard.conf
  echo 'INTERVAL=$INTERVAL' >> /mnt/us/dashboard.conf
  chmod +x /mnt/us/start.sh /mnt/us/stop.sh
  /usr/sbin/mntroot rw 2>/dev/null || true
  grep -v '/mnt/us/start.sh' /etc/crontab/root > /tmp/cr.tmp 2>/dev/null && mv /tmp/cr.tmp /etc/crontab/root
  echo '@reboot sleep 30 && /mnt/us/start.sh # kindle-dashboard' >> /etc/crontab/root
  /usr/sbin/mntroot ro 2>/dev/null || true
  command -v fbink >/dev/null 2>&1 || echo 'WARN: 未找到 fbink,刷屏会失败 —— 请通过 KUAL/越狱工具安装 fbink 后重跑'
  setsid /mnt/us/start.sh < /dev/null > /mnt/us/dashboard.log 2>&1 &
  echo started
"

# 实测 .local 兜底在这台 Kindle 上能否解析(把"需真机验证 mDNS"这步自动化掉)
if [ -n "$SERVER_URL_ALT" ]; then
  echo "==> 测试备用地址 $SERVER_URL_ALT 在此 Kindle 上是否可用..."
  code=$(ssh $SSHOPT root@"$KINDLE_IP" "curl -s -m 6 -o /dev/null -w '%{http_code}' $SERVER_URL_ALT/health 2>/dev/null" 2>/dev/null) || code=000
  if [ "$code" = "200" ]; then
    echo "   ✓ 可用:Mac 局域网 IP 变了也能自动切到 .local,无需手动改地址。"
  else
    echo "   ⚠ 此 Kindle 解析不了 .local(busybox 多半无 mDNS,实测返回「${code:-无}」)。"
    echo "     → Mac IP 会变,多半是 Apple『私有 Wi-Fi 地址』在轮替 MAC。解决:系统设置→Wi-Fi→"
    echo "       当前网络『详细信息』→『私有 Wi-Fi 地址』从『轮替』改成『固定』,IP 通常就稳定了。"
    echo "       (想 100% 保险:固定后再去路由器把该 MAC 绑定一个 IP。详见 docs/install.md)"
  fi
fi

# 关闭复用连接
ssh $SSHOPT -O exit root@"$KINDLE_IP" 2>/dev/null || true

echo "✓ 完成。Kindle 应开始显示看板(横放摆,顶边朝右)。"
echo "  之后改配置在网页保存即可,Kindle 侧不用再碰。"
echo "  不想用了:sh installers/kindle/uninstall.sh $KINDLE_IP"
