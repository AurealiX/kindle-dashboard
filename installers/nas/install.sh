#!/bin/bash
# Kindle Dashboard NAS 部署(Docker)
#
# 用法:在 NAS 上克隆仓库后,cd 到仓库根目录运行:
#   bash installers/nas/install.sh
#
# 做三件事:
#   1) docker compose build + up -d
#   2) 等服务健康,打印设置页地址(含访问令牌)
#   3) 打印 Mac 侧推送命令(提醒/额度/ccusage 指向 NAS)

set -e

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_DIR="$REPO/installers/nas"

die(){ echo "✗ $1"; exit 1; }

# 检查 docker
command -v docker >/dev/null 2>&1 || die "未找到 docker,请先安装 Docker。"
docker compose version >/dev/null 2>&1 || docker-compose version >/dev/null 2>&1 || die "未找到 docker compose 插件。"

# 检查是否用 docker compose 还是 docker-compose
if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
else
    COMPOSE="docker-compose"
fi

echo "=== Kindle Dashboard NAS 部署 ==="
echo

# 构建并启动
echo ">> 构建镜像并启动服务..."
cd "$COMPOSE_DIR"
$COMPOSE up -d --build

echo
echo ">> 等待服务就绪..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8585/health >/dev/null 2>&1; then
        echo "✓ 服务已就绪"
        break
    fi
    [ "$i" -eq 30 ] && die "服务 30 秒内未就绪,请检查 docker logs kindle-dashboard"
    sleep 1
done

# 获取 NAS 局域网 IP
NAS_IP=""
for ip in $(hostname -I 2>/dev/null || ifconfig 2>/dev/null | grep -oE 'inet [0-9.]+' | awk '{print $2}'); do
    case "$ip" in
        192.168.*|10.*) NAS_IP="$ip"; break ;;
        172.*)
            second=$(echo "$ip" | cut -d. -f2)
            [ "$second" -ge 16 ] && [ "$second" -le 31 ] && NAS_IP="$ip" && break
            ;;
    esac
done
[ -z "$NAS_IP" ] && NAS_IP="<NAS_IP>"
NAS_URL="http://$NAS_IP:8585"

# 获取访问令牌(从容器日志里抓)
TOKEN=$(docker logs kindle-dashboard 2>&1 | grep -oP 'token=\K[A-Za-z0-9_-]+' | tail -1)

echo
echo "=========================================="
echo "  Kindle Dashboard 已在 NAS 上运行"
echo "=========================================="
echo
echo "设置页:  $NAS_URL/setup${TOKEN:+?token=$TOKEN}"
echo "健康检查: $NAS_URL/health"
echo "Kindle:  $NAS_URL/kindle/frame.png"
echo
echo "=========================================="
echo "  Mac 侧推送命令(在跑 Claude/Codex 的 Mac 上执行)"
echo "=========================================="
echo
echo "# 1. AI 用量(ccusage)推送到 NAS:"
echo "bash installers/macos/enable_ccusage_push.sh --url $NAS_URL"
echo
echo "# 2. 提醒事项推送到 NAS:"
echo "bash installers/macos/enable_reminders.sh --url $NAS_URL"
echo
echo "# 3. AI 额度推送到 NAS:"
echo "bash installers/macos/enable_quota.sh --url $NAS_URL"
echo
echo "# 4. 设备监控 agent(在要监控的机器上执行):"
echo "curl -fsSL $NAS_URL/agent/install.sh | sh -s -- $NAS_URL 30"
echo
echo "=========================================="
echo
echo "停止: cd $COMPOSE_DIR && $COMPOSE down"
echo "日志: docker logs -f kindle-dashboard"
echo "重建: cd $COMPOSE_DIR && $COMPOSE up -d --build"
