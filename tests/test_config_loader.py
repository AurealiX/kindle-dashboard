"""配置加载器验证。可直接 `python3 tests/test_config_loader.py` 跑,也兼容 pytest。"""
import os
import sys
import tempfile

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server.config import loader, schema  # noqa: E402


def _tmp():
    return os.path.join(tempfile.mkdtemp(), "config.yaml")


def test_missing_file_uses_default():
    cm = loader.ConfigManager(_tmp())
    assert cm.status()["config_exists"] is False
    assert cm.errors() == []
    assert cm.get()["server"]["port"] == 8585


def test_load_merges_file_over_default():
    p = _tmp()
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump({"server": {"port": 9000}}, f)
    cm = loader.ConfigManager(p)
    assert cm.get()["server"]["port"] == 9000          # 文件覆盖
    assert cm.get()["server"]["timezone"] == "Asia/Shanghai"  # 缺项补默认


def test_maybe_reload_detects_change():
    p = _tmp()
    cm = loader.ConfigManager(p)            # 文件不存在
    assert cm.get()["server"]["port"] == 8585
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump({"server": {"port": 7000}}, f)
    assert cm.maybe_reload() is True
    assert cm.get()["server"]["port"] == 7000
    assert cm.maybe_reload() is False       # 没变,不重载


def test_save_rejects_invalid():
    """启用 HA(填 url)但缺 token → save 失败、不写盘。"""
    p = _tmp()
    cm = loader.ConfigManager(p)
    errs = cm.save({"home_assistant": {"url": "http://x:8123"}})
    assert errs and any("令牌" in e for e in errs)
    assert not os.path.exists(p)            # 校验没过不落盘


def test_save_persists_and_reloads():
    p = _tmp()
    cm = loader.ConfigManager(p)
    errs = cm.save({"weather": {"key": "abc", "location": "101010100"}})
    assert errs == []
    assert os.path.exists(p)
    cm2 = loader.ConfigManager(p)           # 新实例读回
    assert cm2.get()["weather"]["key"] == "abc"
    assert "home" in cm2.status()["active_pages"]


def test_redacted_masks_secret():
    p = _tmp()
    cm = loader.ConfigManager(p)
    cm.save({"weather": {"key": "supersecret", "location": "101010100"}})
    red = cm.redacted()
    assert red["weather"]["key"] == loader.SECRET_MASK   # 不吐真实值
    assert red["weather"]["location"] == "101010100"     # 非密钥照常


def test_secret_preserved_when_mask_submitted():
    """前端回显掩码,用户没改 key 就提交 → 原 key 不被清空。"""
    p = _tmp()
    cm = loader.ConfigManager(p)
    cm.save({"weather": {"key": "realkey", "location": "101010100"}})
    cm.save({"weather": {"key": loader.SECRET_MASK, "location": "101010100"}})
    assert cm.get()["weather"]["key"] == "realkey"


def test_device_list_secret_preserved():
    p = _tmp()
    cm = loader.ConfigManager(p)
    cm.save({"devices": {"machines": [
        {"name": "srv", "mode": "ssh", "host": "1.2.3.4", "ssh_user": "u", "ssh_password": "pw"}]}})
    # 再保存,密码提交空 → 保留
    cm.save({"devices": {"machines": [
        {"name": "srv", "mode": "ssh", "host": "1.2.3.4", "ssh_user": "u", "ssh_password": ""}]}})
    assert cm.get()["devices"]["machines"][0]["ssh_password"] == "pw"


def test_saved_file_is_valid_yaml_no_tmp():
    p = _tmp()
    cm = loader.ConfigManager(p)
    cm.save({"server": {"port": 8080}})
    with open(p, encoding="utf-8") as f:
        yaml.safe_load(f)                   # 合法 yaml
    assert not os.path.exists(p + ".tmp")   # 无残留临时文件


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} passed")
