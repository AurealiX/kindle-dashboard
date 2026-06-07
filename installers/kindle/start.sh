#!/bin/sh
# Kindle 端拉图显示脚本(推送到 /mnt/us/)。服务地址从 dashboard.conf 读,不写死。
# 装机时由主机端 install.sh 写入 /mnt/us/dashboard.conf:
#   SERVER_URL=http://<服务IP>:<端口>
. /mnt/us/dashboard.conf 2>/dev/null
SERVER_URL="${SERVER_URL:-http://192.168.1.100:8585}"
SERVER_URL_ALT="${SERVER_URL_ALT:-}"   # 备用地址(Mac 的 .local mDNS 名);主地址(IP)失效时自动切
INTERVAL="${INTERVAL:-20}"
CLEAR_EVERY="${CLEAR_EVERY:-10}"

PIDFILE="/mnt/us/dashboard.pid"
BASE="$SERVER_URL"                     # 当前实际使用的服务地址;拉图连续失败会在主/备间轮换自愈

report_battery() {
    batt=$(lipc-get-prop com.lab126.powerd battLevel 2>/dev/null)
    chg=$(lipc-get-prop com.lab126.powerd isCharging 2>/dev/null)
    [ -z "$batt" ] && return
    if [ "$chg" = "1" ]; then chg_b="true"; else chg_b="false"; fi
    curl -s -m 5 -X POST "$BASE/api/kindle-status" -H "Content-Type: application/json" \
        -d "{\"battery\":$batt,\"charging\":$chg_b}" >/dev/null 2>&1
}

ensure_wifi() {
    state=$(timeout 5 wpa_cli status 2>/dev/null | grep 'wpa_state=' | cut -d= -f2)
    if [ "$state" != "COMPLETED" ]; then
        timeout 5 lipc-set-prop com.lab126.cmd wirelessEnable 1 2>/dev/null
        timeout 5 wpa_cli reconnect 2>/dev/null
        sleep 5
        state=$(timeout 5 wpa_cli status 2>/dev/null | grep 'wpa_state=' | cut -d= -f2)
        [ "$state" != "COMPLETED" ] && sleep 10
    fi
    lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null
}

# 杀旧实例
if [ -f "$PIDFILE" ]; then
    kill $(cat "$PIDFILE") 2>/dev/null
    rm -f "$PIDFILE"
fi
echo $$ > "$PIDFILE"

# 1. 杀看门狗 pmond(否则杀界面后会自动重启)
kill $(pidof pmond) 2>/dev/null
sleep 1
# 2. 杀图形界面进程,独占屏幕
for p in cvm awesome blanket lxinit KPPMainApp pillowd JunoStatusBarDriver kfxreader mesquite; do
    kill $(pidof $p) 2>/dev/null
done
sleep 2
# 3. 防休眠
lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null
# 4. 首屏
ensure_wifi
report_battery
curl -s -m 10 "$BASE/kindle/frame.png" -o /mnt/us/frame.png
fbink -c -f
fbink -g file=/mnt/us/frame.png -W GC16 -f

# 5. 主循环 + WiFi 看门狗
count=0; fail=0
while true; do
    sleep "$INTERVAL"
    curl -s -m 10 "$BASE/kindle/frame.png" -o /mnt/us/frame_new.png
    if [ -s /mnt/us/frame_new.png ]; then
        mv /mnt/us/frame_new.png /mnt/us/frame.png
        fail=0
    else
        fail=$((fail + 1))
        [ $((fail % 3)) -eq 0 ] && ensure_wifi   # 连续3次(~60s)失败先重连 WiFi
        # 再失败可能是 Mac 局域网 IP 变了(DHCP):在主(IP)/备(.local)地址间轮换,通了就留在新地址
        if [ -n "$SERVER_URL_ALT" ] && [ $((fail % 6)) -eq 0 ]; then
            if [ "$BASE" = "$SERVER_URL" ]; then BASE="$SERVER_URL_ALT"; else BASE="$SERVER_URL"; fi
        fi
    fi
    count=$((count + 1))
    [ $((count % 3)) -eq 0 ] && report_battery
    if [ $((count % CLEAR_EVERY)) -eq 0 ]; then
        fbink -g file=/mnt/us/frame.png -W GC16 -f   # 定期全刷去残影
    else
        fbink -g file=/mnt/us/frame.png -W REAGL
    fi
done
