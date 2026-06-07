"""macOS 菜单栏:显示看板服务运行状态 + 控制(打开设置/重启/启停/退出)。

仅 macOS(依赖 rumps/PyObjC,requirements.txt 用 marker 仅在 darwin 安装)。
由 LaunchAgent 登录自启:.venv/bin/python -m server.menubar
读 config.yaml 的端口,每 5 秒轮询 /health 更新状态:● 运行中 / ○ 已停。
"""
import os
import subprocess
import urllib.request
import webbrowser

import rumps

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLIST = os.path.expanduser("~/Library/LaunchAgents/com.kindle-dashboard.plist")


def _port():
    try:
        import yaml
        with open(os.path.join(REPO, "config.yaml"), encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return int(cfg.get("server", {}).get("port", 8585))
    except Exception:
        return 8585


class DashboardBar(rumps.App):
    def __init__(self):
        super().__init__("○ 看板", quit_button=None)
        self.port = _port()
        # 启停分两个独立项,避免动态改标题导致回调失效
        self.menu = ["打开设置页", "重启服务", "启动服务", "停止服务", None, "退出菜单栏"]
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
        self.title = "● 看板" if self._alive() else "○ 看板"

    @rumps.clicked("打开设置页")
    def _open(self, _):
        webbrowser.open("http://127.0.0.1:%d/setup" % self.port)

    @rumps.clicked("重启服务")
    def _restart(self, _):
        subprocess.run(["launchctl", "unload", PLIST], capture_output=True)
        subprocess.run(["launchctl", "load", PLIST], capture_output=True)
        self.refresh()

    @rumps.clicked("启动服务")
    def _start(self, _):
        subprocess.run(["launchctl", "load", PLIST], capture_output=True)
        self.refresh()

    @rumps.clicked("停止服务")
    def _stop(self, _):
        subprocess.run(["launchctl", "unload", PLIST], capture_output=True)
        self.refresh()

    @rumps.clicked("退出菜单栏")
    def _quit(self, _):
        rumps.quit_application()   # 只退菜单栏,看板服务继续后台运行


def main():
    DashboardBar().run()


if __name__ == "__main__":
    main()
