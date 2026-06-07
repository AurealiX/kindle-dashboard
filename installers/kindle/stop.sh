#!/bin/sh
# Kindle 端:停止看板并恢复系统界面(推送到 /mnt/us/)。
PIDFILE="/mnt/us/dashboard.pid"

if [ -f "$PIDFILE" ]; then
    kill $(cat "$PIDFILE") 2>/dev/null
    rm -f "$PIDFILE"
    echo "Dashboard stopped"
else
    echo "Dashboard not running"
fi

# 恢复界面与看门狗
lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
/sbin/initctl start framework 2>/dev/null || true
/sbin/initctl start pmond 2>/dev/null || true
echo "Framework restored. If display is stuck, reboot the Kindle."
