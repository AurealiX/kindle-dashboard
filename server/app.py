"""主服务:FastAPI app。串起 配置热重载 → 数据采集 → 整合 → 渲染 → 出图,
并提供 Kindle 取图、实时预览、push 接收、设置网页 API。

配置即页面:渲染哪些页由 active_pages(cfg) 决定(数据源没配的页不渲染)。
诚实降级:采集/渲染单点失败只跳过该项,保留旧页;全失败杀僵尸下轮恢复。
"""
import io
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Body, Request
from fastapi.responses import Response, HTMLResponse, JSONResponse

from server.config import schema
from server.config.loader import ConfigManager
from server.render import styles, pipeline, contract
from server.render.build_context import prep_context
from server.sources import weather, ccusage_cli, homeassistant, metrics, mstodo
from server.sources.ccusage_merge import merge_all_devices

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_config_path(env=None, new_default=None, old_default=None):
    """配置文件路径 —— **外置到仓库外**(`~/.config/kindle-dashboard/config.yaml`),
    这样 git 升级 / 重装 / 删库重拉都不丢用户配置(凭据/城市/设备全在)。
    `KINDLE_CONFIG` 环境变量可覆盖。
    自动迁移:外置位置还没有、但仓库内有旧 `config.yaml` 时,搬出来一份(老用户无感)。"""
    env = env if env is not None else os.environ.get("KINDLE_CONFIG")
    if env:
        return env
    new = new_default or os.path.expanduser("~/.config/kindle-dashboard/config.yaml")
    old = old_default if old_default is not None else os.path.join(REPO_ROOT, "config.yaml")
    if not os.path.exists(new) and old and os.path.exists(old):
        try:
            os.makedirs(os.path.dirname(new), exist_ok=True)
            shutil.copy2(old, new)
            print(f"[config] 已把配置迁移到 {new}(以后升级/重装不再丢设置)")
        except Exception as e:
            print(f"[config] 迁移失败,沿用旧路径 {old}: {e}")
            return old
    return new


CONFIG_PATH = _resolve_config_path()
WEB_DIR = os.path.join(REPO_ROOT, "web")
DATA_DIR = os.environ.get("KINDLE_DATA_DIR", os.path.join(REPO_ROOT, "data"))
APPLE_REMINDERS_CACHE = os.environ.get(
    "KINDLE_APPLE_REMINDERS_CACHE", os.path.join(DATA_DIR, "apple_reminders.json"))
CCUSAGE_DEVICES_CACHE = os.path.join(DATA_DIR, "ccusage_devices.json")

# 推送 agent 脚本(被监控机 curl 下载):白名单路径,纯文本下发
AGENT_FILES = {
    "install.sh":        os.path.join(REPO_ROOT, "installers", "push-agent", "install_agent.sh"),
    "push_agent.sh":     os.path.join(REPO_ROOT, "installers", "push-agent", "push_agent.sh"),
    "collect_linux.sh":  os.path.join(REPO_ROOT, "server", "sources", "collectors", "collect_linux.sh"),
    "collect_macos.sh":  os.path.join(REPO_ROOT, "server", "sources", "collectors", "collect_macos.sh"),
    "install.ps1":       os.path.join(REPO_ROOT, "installers", "push-agent", "install_agent.ps1"),
    "push_agent.ps1":    os.path.join(REPO_ROOT, "installers", "push-agent", "push_agent.ps1"),
    "collect_windows.ps1": os.path.join(REPO_ROOT, "server", "sources", "collectors", "collect_windows.ps1"),
    # Mac 独立推送安装器(NAS 部署用,不需要 clone 仓库)
    "install_reminders.sh": os.path.join(REPO_ROOT, "installers", "mac-push", "install_reminders.sh"),
    "install_ccusage.sh":   os.path.join(REPO_ROOT, "installers", "mac-push", "install_ccusage.sh"),
    "install_quota.sh":     os.path.join(REPO_ROOT, "installers", "mac-push", "install_quota.sh"),
    "read_reminders.js":    os.path.join(REPO_ROOT, "installers", "macos", "reminders", "read_reminders.js"),
    "claude_statusline.py": os.path.join(REPO_ROOT, "installers", "macos", "quota", "claude_statusline.py"),
    "codex_quota.py":       os.path.join(REPO_ROOT, "installers", "macos", "quota", "codex_quota.py"),
}

# 采集器模块名 → (配置段, 字段, 默认秒)。间隔放在各源自己的配置段里(随源卡),不再集中。
SOURCE_INTERVAL = {"weather":       ("weather", "interval", 600),
                   "ccusage_cli":   ("ai_usage", "interval", 300),
                   "homeassistant": ("home_assistant", "interval", 60),
                   "metrics":       ("devices", "interval", 30),
                   "mstodo":        ("mstodo", "interval", 600)}
# 渲染间隔放在「服务」段
RENDER_INTERVAL = ("server", "render_interval", 30)

cm = ConfigManager(CONFIG_PATH)

cache = {}
cache_lock = threading.Lock()

RENDERED = {}            # {page_key: png bytes}
RENDER_ORDER = []        # 当前轮播顺序
RENDER_LOCK = threading.Lock()
CURRENT = {"style": None}
page_state = {"i": 0, "last": 0.0}

SOURCES = (weather, ccusage_cli, homeassistant, metrics, mstodo)
CONFIG_SAVE_SYNC_SOURCES = (weather,)


def _atomic_json_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _apple_payload(data):
    reminders = data.get("reminders", [])
    if not isinstance(reminders, list):
        reminders = []
    return {
        "updated_at": data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        "reminders": reminders,
    }


def _load_apple_reminders_cache():
    """服务重启后回放上次 Apple 提醒,避免等下一轮 launchd 推送前首页空掉。"""
    try:
        with open(APPLE_REMINDERS_CACHE, encoding="utf-8") as f:
            payload = json.load(f) or {}
    except FileNotFoundError:
        return
    except Exception as e:
        print(f"[apple-sync] 读取本地缓存失败:{e}")
        return
    reminders = payload.get("reminders") or []
    if not isinstance(reminders, list):
        return
    with cache_lock:
        cache["reminders"] = reminders
        cache["apple_updated"] = payload.get("updated_at")
    print(f"[apple-sync] 已加载本地缓存 {len(reminders)} 条")


def _is_local_host(host):
    host = (host or "").strip().lower().strip("[]")
    return host in {"localhost", "0.0.0.0", "::", "::1"} or host.startswith("127.")


def _valid_lan_ip(ip):
    return bool(ip and not ip.startswith(("127.", "169.254.")) and ip != "0.0.0.0")


def _lan_priority(ip):
    """局域网地址优先级(越小越优先)。常见家用/办公 LAN 段(RFC1918)优先;
    VPN/代理 TUN(Clash 等用 198.18.0.0/15)、CGNAT(100.64/10)等垫底,
    避免开着代理时把 198.18.0.1 这种虚拟网卡地址当成看板局域网地址。"""
    if ip.startswith("192.168."):
        return 0
    if ip.startswith("10."):
        return 1
    if ip.startswith("172."):
        try:
            if 16 <= int(ip.split(".")[1]) <= 31:    # 172.16.0.0/12
                return 2
        except (ValueError, IndexError):
            pass
    return 9   # 198.18.x(代理 TUN)/100.64.x(CGNAT)等非典型 LAN,排最后


def _lan_ips():
    """尽力找本机可被局域网访问的 IPv4;第一个优先用于生成远程 agent 命令。"""
    ips = []

    def add(ip):
        if _valid_lan_ip(ip) and ip not in ips:
            ips.append(ip)

    for target in ("8.8.8.8", "1.1.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((target, 80))
            add(s.getsockname()[0])
            s.close()
            break
        except Exception:
            try:
                s.close()
            except Exception:
                pass

    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            add(ip)
    except Exception:
        pass

    for cmd in (("ip", "-4", "-o", "addr", "show", "scope", "global"), ("ifconfig",)):
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=2)
        except Exception:
            continue
        for ip in re.findall(r"\binet\s+(\d+\.\d+\.\d+\.\d+)", out):
            add(ip)
    # 按家用 LAN 段优先排序(稳定排序保留同级原有顺序):真实局域网 IP 排前,
    # 代理/VPN 的 198.18.x 之类垫底,recommended=ips[0] 才不会误选虚拟网卡地址。
    ips.sort(key=_lan_priority)
    return ips


def _local_hostname_url(scheme, port):
    """本机 mDNS `.local` 地址(如 http://Xxx.local:8585)。
    支持 mDNS 的设备(多数 Mac / Linux / 手机)用它当看板地址,可**绕开 IP 漂移**(IP 变了名字不变);
    不支持 mDNS 的设备(如部分 Kindle busybox)忽略即可。取不到名字则返回 ''(不臆造)。"""
    name = ""
    try:                                  # macOS:LocalHostName 就是 .local 名(不含后缀)
        r = subprocess.run(["scutil", "--get", "LocalHostName"],
                           capture_output=True, text=True, timeout=2)
        if r.returncode == 0:
            name = r.stdout.strip()
    except Exception:
        pass
    if not name:                          # 非 macOS:仅当主机名本身就是 .local 才用,不凭空造
        try:
            h = socket.gethostname().strip()
            if h.endswith(".local"):
                name = h[:-6]
        except Exception:
            pass
    if not name or any(c in name for c in " \t/\\"):
        return ""
    return f"{scheme}://{name}.local:{port}"


_load_apple_reminders_cache()


def _load_ccusage_devices_cache():
    """服务重启后回放各设备推送的 ccusage 数据,重算合并结果,避免重启后空窗。"""
    try:
        with open(CCUSAGE_DEVICES_CACHE, encoding="utf-8") as f:
            by_device = json.load(f) or {}
    except FileNotFoundError:
        return
    except Exception as e:
        print(f"[ccusage-push] 读取设备缓存失败:{e}")
        return
    if not isinstance(by_device, dict) or not by_device:
        return
    merged = merge_all_devices(by_device)
    with cache_lock:
        cache.setdefault("ccusage_by_device", {}).update(by_device)
        cache["ccusage"] = merged
    print(f"[ccusage-push] 已加载 {len(by_device)} 台设备的缓存")


_load_ccusage_devices_cache()


def _tz(cfg):
    name = cfg.get("server", {}).get("timezone", "Asia/Shanghai")
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return timezone(timedelta(hours=8))


# ---------- 采集 + 渲染 ----------
def _merge(frag):
    if not frag:
        return
    with cache_lock:
        for k, v in frag.items():
            if k == "devices_metrics":
                # 只更新本轮成功项;单台临时失败保留上一帧(不删)。改名/删除的旧指标由
                # _prune_pull_device_cache(配置保存时)剪——别在这无脑删非 push 项,否则 A 成功 B 失败时 B 凭空消失。
                cache.setdefault("devices_metrics", {}).update(v)
            else:
                cache[k] = v


def _prune_pull_device_cache(cfg):
    """配置保存后剪掉已改名/已删除的本机或 SSH 指标;push 设备继续保留供发现区使用。"""
    machines = ((cfg or {}).get("devices", {}) or {}).get("machines", []) or []
    keep = {
        (m.get("id") or "").strip() or (m.get("name") or "").strip()
        for m in machines
        if (m.get("mode") or "local") != "push"
    }
    keep = {x for x in keep if x}
    with cache_lock:
        cur = cache.get("devices_metrics") or {}
        for key, val in list(cur.items()):
            if not val.get("updated_at") and key not in keep:
                cur.pop(key, None)


def collect_source(src, cfg):
    try:
        _merge(src.collect(cfg))
    except Exception as e:
        print(f"[collect] {src.__name__}: {e}")


def render_all(cfg):
    now = datetime.now(_tz(cfg))
    style = styles.pick_style(cfg, now.date())
    if not style:
        return
    rc = pipeline.RenderConfig.from_config(cfg)
    pages = schema.active_pages(cfg)
    with cache_lock:
        ctx = prep_context(now, dict(cache), cfg)
    new = {}
    for pk in pages:
        if not styles.has_page(style, pk):
            continue
        try:
            new[pk] = pipeline.render_html_to_png(styles.render_page(style, pk, ctx), rc)
        except Exception as e:
            print(f"[render] {pk}: {e}")
    if not new:
        if pages:        # 有启用页却全失败=真僵尸,才清理;无启用页(还没配数据源)不算失败,别瞎杀
            pipeline.kill_stale_chrome()
            print("[render] 全部失败,已杀僵尸,下轮恢复")
        return
    with RENDER_LOCK:
        for pk in new:
            RENDERED[pk] = new[pk]
        RENDER_ORDER[:] = [p for p in pages if p in RENDERED]
        CURRENT["style"] = style


def _interval(cfg, section, field, default):
    """取某配置段某字段的间隔(秒)。缺失/非法 → 回落默认;最低 5 秒防忙转。"""
    try:
        v = int((cfg.get(section, {}) or {}).get(field))
    except (TypeError, ValueError):
        v = 0
    return max(5, v) if v else default


def source_loop(src):
    """每个数据源一条独立线程,按各自间隔采集,互不阻塞(慢源如 ccusage 不再拖累渲染)。"""
    section, field, default = SOURCE_INTERVAL.get(src.__name__.rsplit(".", 1)[-1], RENDER_INTERVAL)
    while True:
        cfg = cm.get()
        collect_source(src, cfg)
        time.sleep(_interval(cfg, section, field, default))


def render_loop():
    """渲染独立线程:按 render 间隔从缓存出图,不受采集快慢影响(时钟永不冻)。
    并负责热重载配置(唯一调 maybe_reload 的线程,避免多线程竞争)。"""
    while True:
        cm.maybe_reload()
        cfg = cm.get()
        try:
            render_all(cfg)
        except Exception as e:
            print(f"[render_all] {e}")
        time.sleep(_interval(cfg, *RENDER_INTERVAL))


def _ensure_access_token():
    """首次启动若没令牌则生成一个,写进 config 并打印带令牌的设置页链接。
    令牌保护设置/配置接口(见 _auth 中间件);Kindle 拉图、设备上报不受影响。"""
    if (cm.get().get("server", {}) or {}).get("access_token"):
        return
    import secrets
    tok = secrets.token_urlsafe(16)
    cm.force_set("server", "access_token", tok)   # 绕过全量校验,别被 config 别处的错误挡掉令牌生成
    port = (cm.get().get("server", {}) or {}).get("port", 8585)
    print("[auth] 已生成设置页访问令牌(只此一份,请记下)。用此链接打开设置页:")
    print(f"       http://<本机IP>:{port}/setup?token={tok}")


def _log_rotate_loop():
    """日志看门狗:每小时把 data/*.log 超 5MB 的截断到只保留最近约 1MB,
    防 launchd 重定向的 service/menubar/codex-quota/reminders 日志长期跑爆盘。"""
    import glob
    MAX, KEEP = 5 * 1024 * 1024, 1 * 1024 * 1024
    while True:
        try:
            for f in glob.glob(os.path.join(DATA_DIR, "*.log")):
                try:
                    if os.path.getsize(f) > MAX:
                        with open(f, "rb") as fp:
                            fp.seek(-KEEP, os.SEEK_END)
                            tail = fp.read()
                        with open(f, "wb") as fp:
                            fp.write("...(日志已轮转,仅保留最近部分)...\n".encode() + tail)
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(3600)


@asynccontextmanager
async def lifespan(_app):
    _ensure_access_token()
    pipeline.kill_stale_chrome()   # 清上一轮残留的渲染 Chrome(重启即自动扫除僵尸,免手动 pkill)
    for src in SOURCES:
        threading.Thread(target=source_loop, args=(src,), daemon=True).start()
    threading.Thread(target=render_loop, daemon=True).start()
    threading.Thread(target=_log_rotate_loop, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


# ---------- 访问鉴权:令牌保护设置/配置接口;Kindle 拉图/设备上报/health 豁免 ----------
from fastapi import Request  # noqa: E402

# 豁免前缀:Kindle 只拉 frame.png / page/*;agent 下发、health、setup 空壳页都放行
_AUTH_EXEMPT_PREFIXES = ("/kindle/frame.png", "/kindle/page/", "/agent/", "/health", "/setup")
# 豁免精确路径:设备主动上报的接口(push 进来,Kindle/agent 调,带不了令牌)
_AUTH_EXEMPT_EXACT = {"/", "/api/device-metrics", "/api/apple-sync",
                      "/api/rate-limits", "/api/kindle-status", "/api/ccusage"}


@app.middleware("http")
async def _auth(request: Request, call_next):
    token = (cm.get().get("server", {}) or {}).get("access_token") or ""
    if token:  # 设了令牌才校验;空=放行(向后兼容,首次启动会自动生成)
        path = request.url.path
        exempt = path in _AUTH_EXEMPT_EXACT or any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES)
        if not exempt:
            given = (request.query_params.get("token")
                     or request.headers.get("X-Access-Token")
                     or request.cookies.get("kd_token") or "")
            if given != token:
                return JSONResponse(
                    {"ok": False, "error": "需要访问令牌:请用 install 打印的 /setup?token=... 链接打开设置页。"},
                    status_code=401)
    return await call_next(request)


# ---------- Kindle 取图 ----------
def _placeholder():
    from PIL import Image, ImageDraw
    img = Image.new("L", (600, 800), 255)
    ImageDraw.Draw(img).text((230, 380), "Loading...", fill=120)
    b = io.BytesIO(); img.save(b, format="PNG"); return b.getvalue()


@app.get("/kindle/frame.png")
def kindle_frame():
    cfg = cm.get()
    interval = cfg.get("server", {}).get("page_interval", 20)
    with RENDER_LOCK:
        order = list(RENDER_ORDER)
        if order:
            now_ts = time.time()
            if page_state["last"] == 0.0:
                page_state["last"] = now_ts          # 首次:停在第 0 页(首页),不立即跳页
            elif now_ts - page_state["last"] >= interval:
                page_state["i"] = (page_state["i"] + 1) % len(order)
                page_state["last"] = now_ts
            png = RENDERED.get(order[page_state["i"] % len(order)])
        else:
            png = None
    return Response(png or _placeholder(), media_type="image/png")


@app.get("/kindle/page/{page_key}.png")
def kindle_page(page_key: str):
    with RENDER_LOCK:
        png = RENDERED.get(page_key)
    return Response(png or _placeholder(), media_type="image/png")


@app.get("/kindle/preview.png")
def kindle_preview(page: str, style: str = ""):
    """实时预览:即时渲染指定页/风格(不走缓存)。设置网页用。"""
    cfg = cm.get()
    s = style or styles.pick_style(cfg)
    if not s:
        return Response(b"no style", media_type="text/plain", status_code=400)
    now = datetime.now(_tz(cfg))
    with cache_lock:
        ctx = prep_context(now, dict(cache), cfg)
    try:
        html = styles.render_page(s, page, ctx)
        rc = pipeline.RenderConfig.from_config(cfg)
        rc.rotate = 0   # 预览用横屏正立(电脑上看舒服;= Kindle 横放后实际所见)。frame.png 仍按配置旋转。
        png = pipeline.render_html_to_png(html, rc)
    except Exception as e:
        return Response(f"render error: {e}".encode(), media_type="text/plain", status_code=500)
    return Response(png, media_type="image/png")


@app.get("/health")
def health():
    cfg = cm.get()
    return {"status": "ok", "style": CURRENT["style"],
            "rendered": sorted(RENDERED.keys()),
            "active_pages": schema.active_pages(cfg)}


# ---------- push 接收 ----------
@app.post("/api/device-metrics")
async def device_metrics(data: dict = Body(...)):
    key = (data.get("id") or data.get("hostname") or "").strip() or "unknown"
    m = data.get("metrics") or {}
    m = dict(m)
    m["hostname"] = data.get("hostname") or key
    m["updated_at"] = time.time()
    with cache_lock:
        dm = cache.setdefault("devices_metrics", {})
        if key not in dm and len(dm) >= 64:   # 防(无鉴权上报口被)恶意/异常 push 大量不同 id 撑爆内存
            return JSONResponse({"status": "rejected", "error": "device count limit"}, status_code=429)
        dm[key] = m
    return {"status": "ok", "key": key}


@app.post("/api/apple-sync")
async def apple_sync(data: dict = Body(...)):
    payload = _apple_payload(data)
    with cache_lock:
        cache["reminders"] = payload["reminders"]
        cache["apple_updated"] = payload["updated_at"]
    try:
        _atomic_json_write(APPLE_REMINDERS_CACHE, payload)
    except Exception as e:
        print(f"[apple-sync] 写本地缓存失败:{e}")
    if payload["reminders"] and not (cm.get().get("reminders", {}) or {}).get("enabled"):
        cm.force_set("reminders", "enabled", True)
    return {"status": "ok"}


@app.post("/api/rate-limits")
async def rate_limits(data: dict = Body(...)):
    source = data.get("source", "claude")
    with cache_lock:
        if source == "codex":
            cache["codex_rate_limits"] = data.get("rate_limits")
        else:
            cache["rate_limits"] = data.get("rate_limits")
    return {"status": "ok"}


@app.post("/api/kindle-status")
async def kindle_status(data: dict = Body(...)):
    with cache_lock:
        cache["kindle_battery"] = data.get("battery")
        cache["kindle_charging"] = data.get("charging", False)
    return {"status": "ok"}


@app.post("/api/ccusage")
async def api_ccusage_push(data: dict = Body(...)):
    """接收设备推送的 ccusage 数据(Mac/其他机器上的 Claude/Codex 日志用量)。
    支持多设备:每台按 id 存储,合并后写入 cache["ccusage"] 供 build_context 消费。"""
    dev_id = (data.get("id") or "").strip() or "unknown"
    cc_data = data.get("cc") or {}
    codex_data = data.get("codex") or {}
    if not isinstance(cc_data, dict):
        cc_data = {}
    if not isinstance(codex_data, dict):
        codex_data = {}
    with cache_lock:
        by_device = cache.setdefault("ccusage_by_device", {})
        if dev_id not in by_device and len(by_device) >= 64:
            return JSONResponse({"status": "rejected", "error": "device count limit"}, status_code=429)
        by_device[dev_id] = {"cc": cc_data, "codex": codex_data}
        merged = merge_all_devices(by_device)
        cache["ccusage"] = merged
    try:
        _atomic_json_write(CCUSAGE_DEVICES_CACHE, by_device)
    except Exception as e:
        print(f"[ccusage-push] 落盘失败：{e}")
    if not (cm.get().get("ai_usage", {}) or {}).get("enabled"):
        cm.force_set("ai_usage", "enabled", True)
    return {"status": "ok", "id": dev_id}


# ---------- 设置网页 API ----------
@app.get("/api/schema")
def api_schema():
    lang = (cm.get().get("server", {}) or {}).get("language", "zh")
    return JSONResponse(schema.to_json(lang))


@app.get("/api/config")
def api_get_config():
    return JSONResponse({"config": cm.redacted(), "status": cm.status()})


@app.post("/api/config")
async def api_save_config(data: dict = Body(...)):
    errors = cm.save(data.get("config") or data)
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)
    cfg = cm.get()
    _prune_pull_device_cache(cfg)
    for src in CONFIG_SAVE_SYNC_SOURCES:
        collect_source(src, cfg)
    return {"ok": True, "status": cm.status()}


@app.get("/api/styles")
def api_styles():
    return {"styles": styles.list_styles(), "pages": list(contract.PAGES.keys())}


@app.get("/agent/{name}")
def agent_file(name: str):
    """下发推送 agent 脚本(被监控机 curl 下载安装)。白名单,纯文本。"""
    path = AGENT_FILES.get(name)
    if not path or not os.path.exists(path):
        return Response("not found", media_type="text/plain", status_code=404)
    with open(path, encoding="utf-8") as f:
        return Response(f.read(), media_type="text/plain; charset=utf-8")


@app.get("/api/city-search")
def api_city_search(q: str = ""):
    """城市搜索:用已保存的天气 host/key 调 GeoAPI,返回候选城市供设置网页选择。
    key 只在服务端使用,不回传前端。"""
    w = cm.get().get("weather", {})
    host = (w.get("host") or "").strip()
    key = (w.get("key") or "").strip()
    if not (host and key):
        return JSONResponse(
            {"ok": False, "error": "请先填写并【保存】天气的 API Host 和 Key,再搜索城市。"},
            status_code=400)
    if not (q or "").strip():
        return {"ok": True, "results": []}
    try:
        results = weather.search_city(host, key, q)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"搜索失败:{e}"}, status_code=502)
    return {"ok": True, "results": results}


@app.get("/api/ha-entities")
def api_ha_entities(q: str = "", domain: str = ""):
    """HA 实体搜索:用已保存的 HA 地址/令牌拉实体,返回候选供设置网页选择。
    令牌只在服务端使用,不回传前端。"""
    ha = cm.get().get("home_assistant", {})
    url = (ha.get("url") or "").strip()
    token = (ha.get("token") or "").strip()
    if not (url and token):
        return JSONResponse(
            {"ok": False, "error": "请先填写并【保存】Home Assistant 的地址和令牌,再选实体。"},
            status_code=400)
    try:
        result = homeassistant.list_entities(url, token, q, domain)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"读取实体失败:{e}"}, status_code=502)
    return {"ok": True, **result}


@app.get("/api/printers")
def api_printers():
    """扫描 HA 中可作为 3D 打印机页数据源的打印机。"""
    ha = cm.get().get("home_assistant", {})
    url = (ha.get("url") or "").strip()
    token = (ha.get("token") or "").strip()
    if not (url and token):
        return JSONResponse(
            {"ok": False, "error": "请先填写并【保存】Home Assistant 的地址和令牌,再扫描打印机。"},
            status_code=400)
    try:
        result = homeassistant.list_printers(url, token)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"扫描打印机失败:{e}"}, status_code=502)
    return {"ok": True, **result}


@app.get("/api/server-url")
def api_server_url(request: Request):
    """给设置页生成远程 agent 命令:localhost 打开设置页时,自动换成局域网地址。"""
    cfg = cm.get()
    origin = str(request.base_url).rstrip("/")
    host = request.url.hostname or ""
    port = request.url.port or int(cfg.get("server", {}).get("port", 8585))
    scheme = request.url.scheme or "http"
    lan_urls = [f"{scheme}://{ip}:{port}" for ip in _lan_ips()]
    use_lan = _is_local_host(host) and lan_urls
    recommended = lan_urls[0] if use_lan else origin
    candidates = []
    for url in [recommended, origin] + lan_urls:
        if url and url not in candidates:
            candidates.append(url)
    local_url = _local_hostname_url(scheme, port)   # mDNS .local:支持的设备可选,绕开 IP 漂移
    if local_url and local_url not in candidates:
        candidates.append(local_url)
    return {
        "origin": origin,
        "recommended": recommended,
        "candidates": candidates,
        "is_loopback": _is_local_host(host),
    }


# ---------- Microsoft To Do 登录(设备码流程) ----------
@app.get("/api/mstodo/state")
def api_mstodo_state():
    """是否已连接 + 账号名(非敏感),供设置页初始渲染。"""
    return {"ok": True, **mstodo.state()}


@app.post("/api/mstodo/login/start")
def api_mstodo_login_start():
    """发起设备码登录,返回用户要输入的 code 和网址。"""
    try:
        return {"ok": True, **mstodo.login_start(cm.get())}
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"发起登录失败:{e}"}, status_code=502)


@app.get("/api/mstodo/login/status")
def api_mstodo_login_status(session: str = ""):
    """轮询登录状态;成功时落地后置 mstodo.enabled=true(只置一次)。"""
    st = mstodo.login_status(session)
    if st.get("state") == "success" and not cm.get().get("mstodo", {}).get("enabled"):
        cm.save({"mstodo": {"enabled": True}})
    return {"ok": True, **st}


@app.post("/api/mstodo/logout")
def api_mstodo_logout():
    """断开连接:删 token + 置 mstodo.enabled=false。"""
    mstodo.logout()
    cm.save({"mstodo": {"enabled": False}})
    return {"ok": True}


@app.get("/api/discovered-devices")
def api_discovered():
    """已上报数据的设备 + 每台可勾选的指标条(供设置网页生成勾选 UI)。"""
    with cache_lock:
        dm = dict(cache.get("devices_metrics", {}))
    out = []
    for key, raw in sorted(dm.items()):
        fields = ["cpu", "mem", "net", "disk_io"]
        fields += [f"vol:{v['name']}" for v in raw.get("disks", [])]
        out.append({"key": key, "hostname": raw.get("hostname", key),
                    "fields": fields, "updated_at": raw.get("updated_at")})
    return {"devices": out}


@app.get("/setup", response_class=HTMLResponse)
def setup_page():
    path = os.path.join(WEB_DIR, "setup.html")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>设置页未安装</h1>", status_code=404)
