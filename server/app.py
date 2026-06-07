"""主服务:FastAPI app。串起 配置热重载 → 数据采集 → 整合 → 渲染 → 出图,
并提供 Kindle 取图、实时预览、push 接收、设置网页 API。

配置即页面:渲染哪些页由 active_pages(cfg) 决定(数据源没配的页不渲染)。
诚实降级:采集/渲染单点失败只跳过该项,保留旧页;全失败杀僵尸下轮恢复。
"""
import io
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Body
from fastapi.responses import Response, HTMLResponse, JSONResponse

from server.config import schema
from server.config.loader import ConfigManager
from server.render import styles, pipeline, contract
from server.render.build_context import prep_context
from server.sources import weather, ccusage_cli, homeassistant, metrics, mstodo

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.environ.get("KINDLE_CONFIG", os.path.join(REPO_ROOT, "config.yaml"))
WEB_DIR = os.path.join(REPO_ROOT, "web")

# 推送 agent 脚本(被监控机 curl 下载):白名单路径,纯文本下发
AGENT_FILES = {
    "install.sh":        os.path.join(REPO_ROOT, "installers", "push-agent", "install_agent.sh"),
    "push_agent.sh":     os.path.join(REPO_ROOT, "installers", "push-agent", "push_agent.sh"),
    "collect_linux.sh":  os.path.join(REPO_ROOT, "server", "sources", "collectors", "collect_linux.sh"),
    "collect_macos.sh":  os.path.join(REPO_ROOT, "server", "sources", "collectors", "collect_macos.sh"),
    "install.ps1":       os.path.join(REPO_ROOT, "installers", "push-agent", "install_agent.ps1"),
    "push_agent.ps1":    os.path.join(REPO_ROOT, "installers", "push-agent", "push_agent.ps1"),
    "collect_windows.ps1": os.path.join(REPO_ROOT, "server", "sources", "collectors", "collect_windows.ps1"),
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
                cache.setdefault("devices_metrics", {}).update(v)
            else:
                cache[k] = v


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
        try:
            _merge(src.collect(cfg))
        except Exception as e:
            print(f"[collect] {src.__name__}: {e}")
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


@asynccontextmanager
async def lifespan(_app):
    for src in SOURCES:
        threading.Thread(target=source_loop, args=(src,), daemon=True).start()
    threading.Thread(target=render_loop, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


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
            if now_ts - page_state["last"] >= interval:
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
        cache.setdefault("devices_metrics", {})[key] = m
    return {"status": "ok", "key": key}


@app.post("/api/apple-sync")
async def apple_sync(data: dict = Body(...)):
    with cache_lock:
        cache["reminders"] = data.get("reminders", [])
        cache["apple_updated"] = data.get("updated_at")
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


# ---------- 设置网页 API ----------
@app.get("/api/schema")
def api_schema():
    return JSONResponse(schema.to_json())


@app.get("/api/config")
def api_get_config():
    return JSONResponse({"config": cm.redacted(), "status": cm.status()})


@app.post("/api/config")
async def api_save_config(data: dict = Body(...)):
    errors = cm.save(data.get("config") or data)
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)
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
