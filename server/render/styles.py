"""风格调度:扫描风格包、按配置选风格、Jinja2 渲染页面。

风格包 = styles/<name>/ 下的 <page>.html(home/ai/device/ha/printer)+ 可选 style.css。
页面文件名 == contract.PAGES 的 key,所有风格共享同一套数据契约(见 docs/data-contract.md)。

风格目录默认在仓库根 styles/;可用 KINDLE_STYLES_DIR 覆盖(测试/自定义路径用)。
"""
import os
import json
import random
from datetime import date

from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound

from server.render.contract import PAGES


def styles_dir() -> str:
    env = os.environ.get("KINDLE_STYLES_DIR")
    if env:
        return env
    # server/render/styles.py → 上三层是仓库根
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "styles")


_envs: dict = {}


def _env(d: str) -> Environment:
    if d not in _envs:
        _envs[d] = Environment(
            loader=FileSystemLoader(d),
            autoescape=select_autoescape(["html"]),
        )
    return _envs[d]


def list_styles(d: str = None) -> list:
    """列出可用风格包(至少含一个页面模板的子目录),按名排序。"""
    d = d or styles_dir()
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        sub = os.path.join(d, name)
        if not os.path.isdir(sub):
            continue
        if any(os.path.exists(os.path.join(sub, f"{p}.html")) for p in PAGES):
            out.append(name)
    return out


def pick_style(cfg: dict, today: date = None, d: str = None) -> str:
    """按配置选风格。fixed→display.style;daily_random→按日期从随机池选。
    选中的风格不存在时回退到第一个可用风格(诚实降级)。"""
    avail = list_styles(d)
    disp = (cfg or {}).get("display", {})
    if disp.get("style_mode") == "daily_random":
        pool = [s for s in (disp.get("style_rotation") or []) if s in avail] or avail
        if not pool:
            return ""
        rng = random.Random((today or date.today()).toordinal())
        return rng.choice(pool)
    chosen = disp.get("style") or "style_a"
    if chosen in avail:
        return chosen
    return avail[0] if avail else ""


def read_css(style: str, d: str = None) -> str:
    path = os.path.join(d or styles_dir(), style, "style.css")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def read_strings(style: str, d: str = None) -> dict:
    """读 styles/<style>/strings.json(i18n 文案表)。结构 {"zh":{...},"en":{...}}。
    缺文件/坏 JSON → 空 dict(诚实降级:模板 {{ t.x }} 渲染为空,不报错)。"""
    path = os.path.join(d or styles_dir(), style, "strings.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def render_page(style: str, page_key: str, ctx: dict, d: str = None) -> str:
    """渲染 styles/<style>/<page_key>.html。模板缺失抛 TemplateNotFound,由上层降级。
    按 ctx['lang'] 注入该风格的文案表 t(英文缺条目回退中文)。"""
    d = d or styles_dir()
    tpl = _env(d).get_template(f"{style}/{page_key}.html")
    full = dict(ctx)
    full["css"] = read_css(style, d)
    lang = (ctx.get("lang") or "zh")
    strings = read_strings(style, d)
    zh = strings.get("zh") or {}
    cur = strings.get(lang) or {}
    full["t"] = {**zh, **cur} if lang != "zh" else zh   # en 缺条目回退中文
    return tpl.render(**full)


def has_page(style: str, page_key: str, d: str = None) -> bool:
    return os.path.exists(os.path.join(d or styles_dir(), style, f"{page_key}.html"))
