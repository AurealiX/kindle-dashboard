"""渲染管线:HTML 字符串 → 无头 Chromium 截图 → PIL 旋转/灰度 → PNG bytes。

Kindle 558 物理屏是 600×800 竖屏。看板横放在显示器下方,所以模板按横屏 800×600 设计,
渲染后旋转 90° 成 600×800 写屏(用户把 Kindle 横过来摆)。Kindle 端照常拉 600×800 图。

尺寸/旋转/灰度全部参数化(从配置 server.render_* 读),不写死。
保留老代码踩过的坑:`--no-crashpad`(防 Chromium 僵尸)、超时杀进程、产物缺失杀僵尸。
ESP32 支线已按开源方案弃用,不再搬运。
"""
import io
import os
import glob
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass

from PIL import Image

_ROT = {
    0: None,
    90: Image.ROTATE_90,     # 逆时针
    180: Image.ROTATE_180,
    270: Image.ROTATE_270,   # 顺时针(默认)
}

# Chrome/Chromium 可执行文件:环境相关,由安装脚本设 CHROME_BIN;否则自动探测。
# 不进 config.yaml(用户业务配置)——用户不该关心二进制路径。
_CANDIDATES = [
    "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
    "/snap/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def _playwright_chrome() -> str:
    """探测 playwright 自动下载的 chromium(venv 内安装,不依赖系统 Chrome)。"""
    home = os.path.expanduser("~")
    patterns = [
        home + "/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
        home + "/.cache/ms-playwright/chromium-*/chrome-linux*/chrome",
    ]
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]   # 取版本号最大的那份
    return ""


def find_chrome() -> str:
    """定位 Chrome/Chromium。优先系统 Chrome,其次 playwright 自带 chromium。找不到返回 ""。"""
    env = os.environ.get("CHROME_BIN")
    if env and os.path.exists(env):
        return env
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        p = shutil.which(name)
        if p:
            return p
    for p in _CANDIDATES:
        if os.path.exists(p):
            return p
    return _playwright_chrome()


# 基准画布(横屏):所有风格只针对它设计,常量,不开放给用户改。
# 改它 = 所有风格要重画。多分辨率靠 device-scale-factor 等比放大,不动 CSS。
BASE_W, BASE_H = 800, 600


@dataclass
class RenderConfig:
    # width/height = 最终输出(用户 Kindle 横屏物理分辨率);base_* = 风格设计的逻辑画布
    width: int = BASE_W
    height: int = BASE_H
    base_width: int = BASE_W
    base_height: int = BASE_H
    rotate: int = 270
    grayscale: bool = True
    timeout: int = 30
    chrome_bin: str = ""

    @classmethod
    def from_config(cls, cfg: dict) -> "RenderConfig":
        s = (cfg or {}).get("server", {})
        # 机型预设→分辨率的映射是 schema 里的唯一数据源(局部导入避免包初始化耦合)
        from server.config.schema import resolve_render_size
        w, h = resolve_render_size(s)
        return cls(
            width=int(w),
            height=int(h),
            base_width=BASE_W,
            base_height=BASE_H,
            rotate=int(s.get("render_rotate", 270)),
            grayscale=bool(s.get("render_grayscale", True)),
            chrome_bin=find_chrome(),
        )


# 渲染串行化:同一时刻只允许一个 Chrome 在跑。
# 关键修复 —— 预览(网页随手点)和主循环(每 render_interval 一轮 5 页)原先各自并发起 Chrome,
# 在低核机器(如 MacBook Air)上几个 Chrome 抢 CPU → 每个都卡过 30s 超时 → 触发清理 → 误杀彼此 → 雪崩。
# 串行化后每次渲染独占资源(基准画布 1~2s 出图),既消除竞态也根除"全部失败"雪崩。
_RENDER_MUTEX = threading.Lock()


def _pkill(pattern: str) -> None:
    """按命令行标记杀进程(只动带该标记的渲染 Chrome,绝不碰本服务/他人进程或用户自己的浏览器)。"""
    try:
        subprocess.run(["pkill", "-9", "-f", pattern], capture_output=True, timeout=5)
    except Exception:
        pass


def kill_stale_chrome() -> None:
    """全局清理本服务**所有**渲染 Chrome(命令行带 kdash-render 标记)。
    仅用于:服务启动时清上一轮残留、以及主循环整轮全失败的兜底扫除。
    单次渲染超时只杀自己那次(见 _shot_to_image 的 _pkill(td)),不走这里,避免误伤。"""
    _pkill("kdash-render")


def _shot_to_image(html: str, rc: RenderConfig) -> Image.Image:
    chrome = rc.chrome_bin or find_chrome()
    if not chrome:
        raise RuntimeError("未找到 Chrome/Chromium,请装 chromium 或设置 CHROME_BIN")
    # 临时目录带 kdash-render 前缀:chrome 命令行会含此路径,kill_stale_chrome 据此只杀自己的渲染进程。
    with tempfile.TemporaryDirectory(prefix="kdash-render-") as td:
        html_path = os.path.join(td, "page.html")
        png_path = os.path.join(td, "out.png")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        # 窗口永远是基准画布(CSS 像素),用 device-scale-factor 把同一份布局矢量放大到
        # 目标物理分辨率 —— 字体/斜线矢量放大依旧锐利,模板 CSS 零改动。
        # scale 取宽/高比的较小值:4:3 机型两者相等;非 4:3 取小值=等比不裁切,短边留白(letterbox)。
        bw = rc.base_width or BASE_W
        bh = rc.base_height or BASE_H
        scale = min(rc.width / bw, rc.height / bh)
        if scale <= 0:
            scale = 1.0
        # 串行化:同一时刻只跑一个 Chrome(预览与主循环互不抢资源)。
        # 超时/缺图时只杀**这次**渲染自己的 Chrome 树(td 路径唯一),不碰其它渲染。
        try:
            with _RENDER_MUTEX:
                subprocess.run([
                    chrome, "--headless", "--no-sandbox", "--disable-gpu",
                    "--no-crashpad", "--disable-crash-reporter",
                    "--disable-dev-shm-usage", "--hide-scrollbars",
                    # 防首启卡顿/后台网络等待(全新 user-data-dir 否则会触发首启流程,在弱机上可拖到超时)
                    "--no-first-run", "--no-default-browser-check",
                    "--disable-background-networking", "--disable-sync",
                    "--disable-default-apps", "--disable-component-update",
                    "--disable-extensions", "--disable-features=Translate,OptimizationHints",
                    "--mute-audio", "--metrics-recording-only",
                    f"--force-device-scale-factor={scale:.4f}",
                    f"--window-size={bw},{bh}",
                    "--default-background-color=FFFFFFFF",
                    f"--user-data-dir={td}/ud",
                    f"--screenshot={png_path}", f"file://{html_path}",
                ], capture_output=True, timeout=rc.timeout)
        except subprocess.TimeoutExpired:
            _pkill(td)      # 只清这次的 Chrome 树,串行下无并发可误伤
            raise
        if not os.path.exists(png_path):
            _pkill(td)
            raise FileNotFoundError("Chromium 未产出截图(已清理本次进程,下轮自动恢复)")
        mode = "L" if rc.grayscale else "RGB"
        shot = Image.open(png_path).convert(mode)
        # 落到精确的输出尺寸:白底居中贴图。兜住两件事——非 4:3 的 letterbox 留白,
        # 以及非整数 scale 取整带来的 1~2px 误差。绝不报错(诚实降级)。
        bg = 255 if mode == "L" else (255, 255, 255)
        canvas = Image.new(mode, (rc.width, rc.height), bg)
        ox = (rc.width - shot.width) // 2
        oy = (rc.height - shot.height) // 2
        canvas.paste(shot, (ox, oy))
        return canvas


def render_html_to_png(html: str, rc: RenderConfig) -> bytes:
    """横屏 HTML → 旋转后的设备 PNG bytes(诚实失败:抛异常,由上层保留旧页)。
    失败自动重试一次 —— headless Chrome 偶发漏图/瞬时超时,重试即自愈,
    避免单次抖动让预览裂图、让该页这一轮空缺。"""
    img = None
    for attempt in range(2):
        try:
            img = _shot_to_image(html, rc)
            break
        except Exception:
            if attempt == 1:
                raise
            time.sleep(0.4)
    rot = _ROT.get(rc.rotate)
    if rot is not None:
        img = img.transpose(rot)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
