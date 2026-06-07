"""HA 实体 → 卡片映射(spec §5)与降级。用 states fixture,不打网络。
可直接 `python3 tests/test_homeassistant.py`,也兼容 pytest。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server.sources import homeassistant as ha  # noqa: E402


# 一份覆盖各 domain / device_class / 降级的 states fixture
STATES = [
    {"entity_id": "light.living", "state": "on",
     "attributes": {"friendly_name": "客厅灯", "icon": "mdi:lightbulb"}},
    {"entity_id": "switch.kettle", "state": "off",
     "attributes": {"friendly_name": "热水壶"}},
    {"entity_id": "sensor.temp", "state": "23.5",
     "attributes": {"friendly_name": "客厅温度", "device_class": "temperature",
                    "unit_of_measurement": "°C"}},
    {"entity_id": "sensor.power", "state": "unavailable",
     "attributes": {"friendly_name": "功率", "device_class": "power",
                    "unit_of_measurement": "W"}},
    {"entity_id": "lock.front", "state": "locked",
     "attributes": {"friendly_name": "前门锁"}},
    {"entity_id": "cover.blind", "state": "open",
     "attributes": {"friendly_name": "窗帘", "current_position": 60}},
    {"entity_id": "binary_sensor.door1", "state": "on",
     "attributes": {"friendly_name": "大门", "device_class": "door"}},
    {"entity_id": "binary_sensor.motion1", "state": "off",
     "attributes": {"friendly_name": "走廊", "device_class": "motion"}},
    {"entity_id": "binary_sensor.leak", "state": "on",
     "attributes": {"friendly_name": "水浸", "device_class": "moisture"}},
    {"entity_id": "climate.ac", "state": "cool",
     "attributes": {"friendly_name": "空调", "current_temperature": 26, "temperature": 24}},
    {"entity_id": "media_player.tv", "state": "playing",
     "attributes": {"friendly_name": "电视", "media_title": "某部名字非常非常长一定会超过十八个字的电影标题"}},
    {"entity_id": "person.me", "state": "home",
     "attributes": {"friendly_name": "我"}},
    {"entity_id": "vacuum.robot", "state": "docked",
     "attributes": {"friendly_name": "扫地机"}},
]
BY_ID = {s["entity_id"]: s for s in STATES}


def card(eid, **ent):
    ent["entity_id"] = eid
    return ha._build_card(BY_ID, ent)


def test_toggle():
    c = card("light.living")
    assert c["kind"] == "toggle" and c["on"] is True and c["state_text"] == "开"
    assert c["icon"] == "mdi:lightbulb"          # 透传 HA 自带 icon
    c2 = card("switch.kettle")
    assert c2["on"] is False and c2["state_text"] == "关"
    assert c2["icon"] == "mdi:power-socket"       # 无自带 → domain 默认


def test_sensor_and_unit():
    c = card("sensor.temp")
    assert c["kind"] == "sensor" and c["value"] == "23.5" and c["unit"] == "°C"
    assert c["on"] is False
    assert c["icon"] == "mdi:thermometer"         # device_class 细分图标


def test_sensor_unavailable_keeps_unit():
    c = card("sensor.power")
    assert c["value"] == "--" and c["unit"] == "W" and c["on"] is False


def test_lock():
    c = card("lock.front")
    assert c["kind"] == "lock" and c["on"] is True and c["state_text"] == "已锁"


def test_cover_position():
    c = card("cover.blind")
    assert c["kind"] == "cover" and c["on"] is True and c["state_text"] == "60%"


def test_binary_classes():
    assert card("binary_sensor.door1")["state_text"] == "开"
    assert card("binary_sensor.motion1")["state_text"] == "无人"
    assert card("binary_sensor.leak")["state_text"] == "漏水"
    assert card("binary_sensor.leak")["on"] is True


def test_climate():
    c = card("climate.ac")
    assert c["kind"] == "climate" and c["on"] is True
    assert c["state_text"] == "制冷" and c["value"] == "26" and c["sub"] == "目标 24°"


def test_media_truncates_title():
    c = card("media_player.tv")
    assert c["kind"] == "media" and c["on"] is True and c["state_text"] == "播放中"
    assert c["sub"].endswith("…") and len(c["sub"]) <= 18


def test_presence():
    c = card("person.me")
    assert c["kind"] == "presence" and c["on"] is True and c["state_text"] == "在家"


def test_unknown_domain_falls_back_to_text():
    c = card("vacuum.robot")
    assert c["kind"] == "text" and c["state_text"] == "docked"   # 兜底:原文,不报错


def test_missing_entity():
    c = card("light.ghost", name="幽灵")
    assert c["state_text"] == "未知实体" and c["kind"] == "text" and c["name"] == "幽灵"


def test_name_and_icon_override():
    c = card("light.living", name="主灯", icon="mdi:ceiling-light")
    assert c["name"] == "主灯" and c["icon"] == "mdi:ceiling-light"


def test_list_entities_filter_and_truncate():
    big = [{"entity_id": f"light.l{i}", "state": "on",
            "attributes": {"friendly_name": f"灯{i}"}} for i in range(60)]
    big.append({"entity_id": "sensor.s1", "state": "1",
                "attributes": {"friendly_name": "传感"}})
    import server.sources.homeassistant as mod
    orig = mod._fetch_states
    mod._fetch_states = lambda url, token: big
    try:
        r = mod.list_entities("http://x", "t", domain="light")
        assert all(e["domain"] == "light" for e in r["entities"])
        assert len(r["entities"]) == 50 and r["truncated"] is True
        r2 = mod.list_entities("http://x", "t", q="传感")
        assert len(r2["entities"]) == 1 and r2["entities"][0]["entity_id"] == "sensor.s1"
    finally:
        mod._fetch_states = orig


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} passed")
