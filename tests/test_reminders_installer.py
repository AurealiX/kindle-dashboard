"""提醒事项启用/停用脚本测试。

复现并锁定的 bug:首次 install.sh 生成的 config 默认 reminders.enabled=false,
旧逻辑"只在 enabled=true 时才装 agent"导致用户在网页开启后 agent 永远不装(死结)。
新方案:install.sh 交互式询问 + enable_reminders.sh / disable_reminders.sh 一键装卸,
agent 生命周期由命令管理,网页给出可复制的命令。

本测试只验证可在 Linux 上验证的部分:配置开关翻转 + 幂等 + 脚本语法。
launchd 安装与 macOS 授权弹窗只能在 Mac 真机验证(KINDLE_SKIP_AGENT=1 跳过)。
"""
import os
import subprocess
import textwrap
import yaml
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENABLE = os.path.join(REPO, "installers/macos/enable_reminders.sh")
DISABLE = os.path.join(REPO, "installers/macos/disable_reminders.sh")
SYNC = os.path.join(REPO, "installers/macos/reminders/sync_reminders.sh")
INSTALL = os.path.join(REPO, "installers/macos/install.sh")
RESTART = os.path.join(REPO, "installers/macos/restart.sh")
UNINSTALL = os.path.join(REPO, "installers/macos/uninstall.sh")
MENUBAR = os.path.join(REPO, "server/menubar.py")


def _run(script, cfg_path):
    env = dict(os.environ, KINDLE_SKIP_AGENT="1", KINDLE_CONFIG=cfg_path)
    return subprocess.run(["bash", script], env=env, capture_output=True, text=True)


def _write_cfg(tmp_path, enabled=False):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump({"server": {"port": 8585},
                                 "reminders": {"enabled": enabled}},
                                allow_unicode=True), encoding="utf-8")
    return str(p)


def _enabled(cfg_path):
    return (yaml.safe_load(open(cfg_path, encoding="utf-8")) or {}).get("reminders", {}).get("enabled")


def test_enable_sets_flag_true(tmp_path):
    cfg = _write_cfg(tmp_path, enabled=False)
    r = _run(ENABLE, cfg)
    assert r.returncode == 0, r.stderr
    assert _enabled(cfg) is True


def test_enable_idempotent(tmp_path):
    cfg = _write_cfg(tmp_path, enabled=False)
    _run(ENABLE, cfg)
    _run(ENABLE, cfg)
    assert _enabled(cfg) is True


def test_disable_sets_flag_false(tmp_path):
    cfg = _write_cfg(tmp_path, enabled=True)
    r = _run(DISABLE, cfg)
    assert r.returncode == 0, r.stderr
    assert _enabled(cfg) is False


def test_enable_preserves_other_config(tmp_path):
    """启用提醒不能动其他配置(端口等)。"""
    cfg = _write_cfg(tmp_path, enabled=False)
    _run(ENABLE, cfg)
    c = yaml.safe_load(open(cfg, encoding="utf-8"))
    assert c["server"]["port"] == 8585


@pytest.mark.parametrize("script", [ENABLE, DISABLE, SYNC, INSTALL, RESTART, UNINSTALL])
def test_bash_syntax_ok(script):
    assert os.path.exists(script), f"脚本不存在:{script}"
    r = subprocess.run(["bash", "-n", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_menubar_installer_uses_lsui_app_bundle():
    text = open(INSTALL, encoding="utf-8").read()
    assert "Kindle Dashboard Menu.app" in text
    assert "<key>LSUIElement</key><true/>" in text
    assert "<array><string>$MB_EXEC</string></array>" in text
    assert "<array><string>$PY</string><string>-m</string><string>server.menubar</string></array>" not in text


def test_uninstall_removes_menubar_app_bundle():
    text = open(UNINSTALL, encoding="utf-8").read()
    assert "Kindle Dashboard Menu.app" in text
    assert 'rm -rf "$MB_APP"' in text


def test_restart_starts_service_even_when_autostart_is_off():
    text = open(RESTART, encoding="utf-8").read()
    assert 'LABEL="com.kindle-dashboard"' in text
    assert 'launchctl start "$LABEL"' in text


def test_menubar_is_icon_only_with_autostart_toggle():
    text = open(MENUBAR, encoding="utf-8").read()
    assert "● 看板" not in text
    assert "○ 看板" not in text
    assert 'title=""' in text or 'title = ""' in text
    # 菜单栏已双语:autostart 文案进 MENU 字典(中英都在)+ 语言切换子菜单
    assert '"开机自启"' in text and '"Start at login"' in text
    assert "_set_lang" in text
    assert "item.state = 1 if checked else 0" in text
    assert 'kwargs["template"] = True' in text
    assert "Resampling" in text
    assert "rounded_rectangle" in text
