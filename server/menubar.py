"""macOS 菜单栏:图标显示 + 看板服务控制。

仅 macOS(依赖 rumps/PyObjC,requirements.txt 用 marker 仅在 darwin 安装)。
由安装脚本生成 LSUIElement app bundle 后交给 LaunchAgent 登录自启。
读 config.yaml 的端口,每 5 秒轮询 /health,状态显示在下拉菜单中。
"""
import os
import plistlib
import subprocess
import urllib.request
import webbrowser

import rumps

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_PATH = os.path.join(REPO, "data", "menubar-icon.png")
SERVICE_LABEL = "com.kindle-dashboard"
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{SERVICE_LABEL}.plist")
CONFIG_PATH = os.path.join(REPO, "config.yaml")

# 菜单文案双语:zh 值与改动前完全一致(回归底线)。
MENU = {
    "zh": {
        "status_checking": "状态: 检测中",
        "status_running": "状态: 运行中",
        "status_stopped": "状态: 已停",
        "autostart": "开机自启",
        "open_setup": "打开设置页",
        "restart": "重启服务",
        "start": "启动服务",
        "stop": "停止服务",
        "quit": "退出菜单栏",
        "language": "语言 / Language",
        "lang_zh": "中文",
        "lang_en": "English",
        "autostart_fail_title": "开机自启设置失败",
        "fail_suffix": "失败",
        "restart_hint_title": "重开菜单栏生效",
        "restart_hint_msg": "语言已切换,请退出并重新打开菜单栏以应用。",
        "plist_not_found": "未找到服务 plist:{path}",
    },
    "en": {
        "status_checking": "Status: checking",
        "status_running": "Status: running",
        "status_stopped": "Status: stopped",
        "autostart": "Start at login",
        "open_setup": "Open settings",
        "restart": "Restart service",
        "start": "Start service",
        "stop": "Stop service",
        "quit": "Quit menu bar",
        "language": "语言 / Language",
        "lang_zh": "中文",
        "lang_en": "English",
        "autostart_fail_title": "Failed to set start-at-login",
        "fail_suffix": " failed",
        "restart_hint_title": "Restart menu bar to apply",
        "restart_hint_msg": "Language changed. Quit and reopen the menu bar to apply.",
        "plist_not_found": "Service plist not found: {path}",
    },
}


def _read_config():
    try:
        import yaml
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _language():
    lang = (_read_config().get("server", {}) or {}).get("language", "zh")
    return lang if lang in MENU else "zh"


def _set_language(lang):
    """写 config.server.language;尽量保留其余配置(直接 yaml 读改写)。"""
    import yaml
    cfg = _read_config()
    cfg.setdefault("server", {})["language"] = lang
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def _hide_dock_icon():
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass


def _ensure_icon():
    try:
        from PIL import Image, ImageDraw
        os.makedirs(os.path.dirname(ICON_PATH), exist_ok=True)
        size = 20
        scale = 4
        img = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        ink = (0, 0, 0, 255)
        def box(values):
            return tuple(int(round(v * scale)) for v in values)

        def px(value):
            return int(round(value * scale))

        # Kindle 外框 + dashboard 信息块,模板图标在深浅菜单栏都可反色。
        d.rounded_rectangle(box((3, 1.8, 17, 18.2)), radius=px(3), outline=ink, width=px(1.7))
        d.rounded_rectangle(box((6, 5, 14, 8)), radius=px(1), fill=ink)
        d.rounded_rectangle(box((6, 10, 9, 13.5)), radius=px(0.8), fill=ink)
        d.rounded_rectangle(box((11, 10, 14, 13.5)), radius=px(0.8), fill=ink)
        d.rounded_rectangle(box((8.2, 16, 11.8, 17)), radius=px(0.5), fill=ink)
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        img.resize((size, size), resampling).save(ICON_PATH)
        return ICON_PATH
    except Exception:
        return None


def _service_autostart_enabled():
    try:
        with open(PLIST, "rb") as f:
            data = plistlib.load(f)
        return bool(data.get("RunAtLoad")) and bool(data.get("KeepAlive"))
    except Exception:
        return False


def _set_service_autostart(enabled):
    with open(PLIST, "rb") as f:
        data = plistlib.load(f)
    data["RunAtLoad"] = bool(enabled)
    data["KeepAlive"] = bool(enabled)
    with open(PLIST, "wb") as f:
        plistlib.dump(data, f, sort_keys=False)


def _port():
    try:
        import yaml
        with open(os.path.join(REPO, "config.yaml"), encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return int(cfg.get("server", {}).get("port", 8585))
    except Exception:
        return 8585


def _launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _start_service():
    if not os.path.exists(PLIST):
        raise FileNotFoundError(
            MENU[_language()]["plist_not_found"].format(path=PLIST))
    _launchctl("load", PLIST)
    _launchctl("start", SERVICE_LABEL)


def _stop_service():
    _launchctl("unload", PLIST)


def _restart_service():
    _launchctl("unload", PLIST)
    _launchctl("load", PLIST)
    _launchctl("start", SERVICE_LABEL)


def _set_checked(item, checked):
    try:
        item.state = 1 if checked else 0
    except Exception:
        pass


class DashboardBar(rumps.App):
    def __init__(self):
        kwargs = {"quit_button": None}
        icon = _ensure_icon()
        if icon:
            kwargs["icon"] = icon
            kwargs["template"] = True
        title = "" if icon else "▣"
        try:
            super().__init__("Kindle Dashboard", title=title, **kwargs)
        except TypeError:
            kwargs.pop("template", None)
            try:
                super().__init__("Kindle Dashboard", title=title, **kwargs)
            except TypeError:
                super().__init__(title, **kwargs)
        self.port = _port()
        self._has_icon = bool(icon)
        self.lang = _language()
        t = MENU[self.lang]
        # 用带 callback 的 MenuItem(而非 @rumps.clicked 装饰器),菜单项标题可随语言变化。
        self.status_item = rumps.MenuItem(t["status_checking"])
        self.autostart_item = rumps.MenuItem(t["autostart"], callback=self._toggle_autostart)
        # 启停分两个独立项,避免动态改标题导致回调失效
        lang_menu = rumps.MenuItem(t["language"])
        self.lang_zh_item = rumps.MenuItem(t["lang_zh"], callback=lambda _: self._set_lang("zh"))
        self.lang_en_item = rumps.MenuItem(t["lang_en"], callback=lambda _: self._set_lang("en"))
        _set_checked(self.lang_zh_item, self.lang == "zh")
        _set_checked(self.lang_en_item, self.lang == "en")
        lang_menu.add(self.lang_zh_item)
        lang_menu.add(self.lang_en_item)
        self.menu = [
            self.status_item, self.autostart_item, None,
            rumps.MenuItem(t["open_setup"], callback=self._open),
            rumps.MenuItem(t["restart"], callback=self._restart),
            rumps.MenuItem(t["start"], callback=self._start),
            rumps.MenuItem(t["stop"], callback=self._stop),
            None, lang_menu, None,
            rumps.MenuItem(t["quit"], callback=self._quit),
        ]
        self._timer = rumps.Timer(self.refresh, 5)
        self._timer.start()
        self.refresh()

    def _alive(self):
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/health" % self.port, timeout=2) as r:
                return b'"status":"ok"' in r.read()
        except Exception:
            return False

    def refresh(self, _=None):
        t = MENU[self.lang]
        self.title = "" if self._has_icon else "▣"
        self.status_item.title = t["status_running"] if self._alive() else t["status_stopped"]
        _set_checked(self.autostart_item, _service_autostart_enabled())

    def _toggle_autostart(self, _):
        enabled = not _service_autostart_enabled()
        try:
            _set_service_autostart(enabled)
            _set_checked(self.autostart_item, enabled)
        except Exception as e:
            rumps.alert(MENU[self.lang]["autostart_fail_title"], str(e))

    def _set_lang(self, lang):
        t = MENU[self.lang]
        try:
            _set_language(lang)
        except Exception as e:
            rumps.alert(MENU[self.lang]["fail_suffix"].strip() or "Error", str(e))
            return
        # rumps 已建好的菜单标题改起来繁琐,直接提示重开菜单栏生效(与设置页"重载"等价)。
        _set_checked(self.lang_zh_item, lang == "zh")
        _set_checked(self.lang_en_item, lang == "en")
        rumps.alert(t["restart_hint_title"], t["restart_hint_msg"])

    def _open(self, _):
        tok = ""
        try:
            tok = (_read_config().get("server", {}) or {}).get("access_token", "") or ""
        except Exception:
            pass
        q = ("?token=" + tok) if tok else ""   # 带令牌才能打开,否则页面里 /api/* 全 401
        webbrowser.open("http://127.0.0.1:%d/setup%s" % (self.port, q))

    def _restart(self, _):
        self._run_control(MENU[self.lang]["restart"], _restart_service)

    def _start(self, _):
        self._run_control(MENU[self.lang]["start"], _start_service)

    def _stop(self, _):
        self._run_control(MENU[self.lang]["stop"], _stop_service)

    def _run_control(self, title, action):
        try:
            action()
        except Exception as e:
            rumps.alert(f"{title}{MENU[self.lang]['fail_suffix']}", str(e))
        self.refresh()

    def _quit(self, _):
        rumps.quit_application()   # 只退菜单栏,看板服务继续后台运行


def main():
    _hide_dock_icon()
    DashboardBar().run()


if __name__ == "__main__":
    main()
