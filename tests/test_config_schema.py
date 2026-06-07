"""配置 schema 的验证。可直接 `python3 tests/test_config_schema.py` 跑,也兼容 pytest。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server.config import schema  # noqa: E402


def test_default_config_validates():
    """默认配置(所有模块未启用)应校验通过 —— 诚实降级:没填不报错。"""
    cfg = schema.default_config()
    errors = schema.validate(cfg)
    assert errors == [], f"默认配置不该有错: {errors}"


def test_default_has_no_secrets():
    """默认/示例里 secret 字段必须为空(零凭据)。"""
    cfg = schema.default_config()
    for sec in schema.SCHEMA:
        for f in sec.fields:
            if f.secret:
                assert cfg[sec.key][f.key] == "", f"{sec.key}.{f.key} 不该带默认凭据"


def test_enable_when_drives_pages():
    """填了天气 key+location → home 页出现;没填 → 不出现。"""
    cfg = schema.default_config()
    assert "home" not in schema.active_pages(cfg)
    cfg["weather"]["key"] = "x"
    cfg["weather"]["location"] = "101010100"
    assert schema.active_pages(cfg) == ["home"]


def test_required_only_checked_when_enabled():
    """HA token 必填,但只在 HA 模块启用(填了 url)时才校验。"""
    cfg = schema.default_config()
    assert schema.validate(cfg) == []          # 没填 url,不强求 token
    cfg["home_assistant"]["url"] = "http://x:8123"
    errors = schema.validate(cfg)
    assert any("令牌" in e for e in errors), f"启用 HA 后应要求 token: {errors}"


def test_devices_enable_and_validate():
    """设备列表:有机器才启用;每台 name 必填。"""
    cfg = schema.default_config()
    assert "device" not in schema.active_pages(cfg)
    cfg["devices"]["machines"] = [{"name": "Mac", "mode": "local"}]
    assert "device" in schema.active_pages(cfg)
    cfg["devices"]["machines"] = [{"name": "", "mode": "local"}]
    assert any("名称" in e for e in schema.validate(cfg))


def test_ha_page_enable_and_pages():
    """ha_page:选了实体才启用、才出 ha 页;空=隐藏(配置即页面)。"""
    cfg = schema.default_config()
    assert "ha" not in schema.active_pages(cfg)
    cfg["ha_page"]["entities"] = [{"entity_id": "light.x", "name": "", "icon": ""}]
    assert "ha" not in schema.active_pages(cfg)        # 只选实体不够,还需 HA 地址/令牌都配好
    cfg["home_assistant"]["url"] = "http://h:8123"
    cfg["home_assistant"]["token"] = "t"
    assert "ha" in schema.active_pages(cfg)
    # entity_id 必填(空 → 报错)
    cfg["ha_page"]["entities"] = [{"entity_id": "", "name": "", "icon": ""}]
    assert any("实体" in e for e in schema.validate(cfg))


def test_type_check():
    cfg = schema.default_config()
    cfg["server"]["port"] = "8585"   # 应为 int
    assert any("端口" in e for e in schema.validate(cfg))


def test_example_yaml_matches_schema():
    """config.example.yaml 的结构必须与 schema 一致(防漂移)。"""
    import yaml
    with open(os.path.join(ROOT, "config.example.yaml"), encoding="utf-8") as fp:
        ex = yaml.safe_load(fp)
    default = schema.default_config()
    assert set(ex.keys()) == set(default.keys()), \
        f"模块不一致: 仅schema={set(default)-set(ex)} 仅example={set(ex)-set(default)}"
    for sec_key, sec_val in default.items():
        assert set(ex[sec_key].keys()) == set(sec_val.keys()), \
            f"[{sec_key}] 字段不一致: 仅schema={set(sec_val)-set(ex[sec_key])} 仅example={set(ex[sec_key])-set(sec_val)}"


def test_to_json_serializable():
    import json
    json.dumps(schema.to_json())  # 不抛异常即可给前端


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} passed")
