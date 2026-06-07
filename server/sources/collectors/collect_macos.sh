#!/bin/sh
# macOS 指标采集 —— 输出统一 JSON(字段同 collect_linux.sh)。
# 基于 top/vm_stat/sysctl/netstat/df 标准命令。⚠️ 待真机(macOS)验证。
# 磁盘 IO 速率 macOS 解析复杂,暂置 0(TODO);cpu/mem/net/分区 已实现。
SLEEP="${COLLECT_INTERVAL:-1}"

# CPU:top -l 2 取第二次采样的 idle(第一次不准)
idle=$(top -l 2 -n 0 -s "$SLEEP" 2>/dev/null | awk '/CPU usage/{i=$7} END{gsub("%","",i); print i}')
cpu=$(awk -v i="${idle:-100}" 'BEGIN{printf "%d", 100 - i}')

# 内存:active + wired + compressed
ps=$(sysctl -n hw.pagesize); mt=$(sysctl -n hw.memsize)
vm=$(vm_stat)
active=$(echo "$vm" | awk '/Pages active/{gsub("\\.","",$3); print $3}')
wired=$(echo "$vm"  | awk '/Pages wired/{gsub("\\.","",$4); print $4}')
comp=$(echo "$vm"   | awk '/occupied by compressor/{gsub("\\.","",$5); print $5}')
mu=$(awk -v a="${active:-0}" -v w="${wired:-0}" -v c="${comp:-0}" -v p="$ps" 'BEGIN{printf "%.0f", (a+w+c)*p}')

# 网络:netstat -ib 两次采样,累加各接口(去重接口名,排除 lo)
read_net() {
  netstat -ib | awk '!seen[$1]++ && $1!~/^lo/ && $7 ~ /^[0-9]+$/ {rx+=$7; tx+=$10} END{printf "%.0f %.0f\n", rx, tx}'
}
set -- $(read_net); rx1=$1; tx1=$2
sleep "$SLEEP"
set -- $(read_net); rx2=$1; tx2=$2
nrx=$(( (rx2 - rx1) / SLEEP )); [ "$nrx" -lt 0 ] && nrx=0
ntx=$(( (tx2 - tx1) / SLEEP )); [ "$ntx" -lt 0 ] && ntx=0

# 分区:仅真实 /dev/ 卷
disks=$(df -k 2>/dev/null | awk '
  $1 ~ /^\/dev\// && $2+0>0 {
    used=$3*1024; total=$2*1024; pct=$5; gsub(/%/,"",pct);
    name=$9; for(i=10;i<=NF;i++) name=name" "$i;
    if (n++) printf ",";
    printf "{\"name\":\"%s\",\"used\":%.0f,\"total\":%.0f,\"pct\":%d}", name, used, total, pct
  }')

printf '{"cpu_pct":%d,"mem_used":%s,"mem_total":%s,"net_rx":%d,"net_tx":%d,"disk_read":0,"disk_write":0,"disks":[%s]}\n' \
  "$cpu" "$mu" "$mt" "$nrx" "$ntx" "$disks"
