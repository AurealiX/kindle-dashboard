"""数据整合层验证:mock cache → prep_context → 符合数据契约。"""
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server.render import build_context as bc          # noqa: E402
from server.render.contract import empty_context        # noqa: E402

NOW = datetime(2026, 6, 7, 14, 30, 5)


def _mock_cache():
    soon = time.time() + 3600
    return {
        "weather_now": {"temp": "24", "text": "多云", "feelsLike": "26",
                        "humidity": "65", "windDir": "西北风", "windScale": "3"},
        "weather_daily": [{"tempMin": "18", "tempMax": "26", "textDay": "多云"},
                          {"tempMin": "19", "tempMax": "27", "textDay": "晴"}],
        "reminders": [
            {"title": "交资料", "dueDate": "2026-06-01", "completed": False},
            {"title": "今天开会", "dueDate": "2026-06-07", "completed": False},
            {"title": "明天体检", "dueDate": "2026-06-08", "completed": False},
            {"title": "已完成的", "dueDate": "2026-06-07", "completed": True},
        ],
        "ccusage": {"ok": True,
                    "cc": {"daily": [{"date": "2026-06-07", "totalTokens": 1_200_000, "totalCost": 8.1}]},
                    "codex": {"daily": [{"date": "2026-06-07", "totalTokens": 600_000, "costUSD": 4.2}]},
                    "customCostCNY": {"total_today": 12.34, "provider_name": "中转站"}},
        "rate_limits": {"five_hour": {"used_percentage": 42, "resets_at": soon},
                        "seven_day": {"used_percentage": 30, "resets_at": soon}},
        "codex_rate_limits": {"five_hour": {"used_percentage": 15, "resets_at": soon},
                              "seven_day": {"used_percentage": 10, "resets_at": soon}},
        "devices_metrics": {"nas-01": {"hostname": "nas-01",
                       "cpu_pct": 23, "mem_used": 8 * 1024**3, "mem_total": 16 * 1024**3,
                       "net_rx": 1_200_000, "net_tx": 300_000,
                       "disk_read": 0, "disk_write": 500_000,
                       "disks": [{"name": "vol1", "pct": 61, "used": 600 * 1024**3, "total": 1024**4}]}},
        "printer": {"online": True, "status": "running", "progress": 47,
                    "task": "benchy.3mf", "layer": "120", "total_layer": "256",
                    "remaining_min": 2.25, "nozzle": "210", "nozzle_t": "210",
                    "bed": "60", "bed_t": "60", "speed": "standard",
                    "weight": "15", "material": "PLA", "cooling_fan": "100",
                    "printer_name": "A1"},
        "kindle_battery": 87, "kindle_charging": False,
    }


def test_full_cache_matches_contract_shape():
    """有数据时,产出的 ctx 顶层结构与 empty_context 同构。"""
    ctx = bc.prep_context(NOW, _mock_cache())
    empty = empty_context()
    assert set(ctx.keys()) >= set(empty.keys()) - {"printer"} | {"printer"}
    for k in ("now", "time_hm", "clock", "battery", "home", "ai", "device", "printer"):
        assert k in ctx, f"缺 {k}"


def test_home_weather_and_reminders():
    ctx = bc.prep_context(NOW, _mock_cache())
    w = ctx["home"]["weather"]
    assert w["temp"] == "24" and w["cond"] == "多云"
    assert w["today_range"] == "18–26°"
    r = ctx["home"]["reminders"]
    assert r["total"] == 3                                  # 排除已完成
    assert any(x["title"] == "交资料" for x in r["overdue"])
    assert any(x["title"] == "今天开会" for x in r["today"])
    assert any(x["title"] == "明天体检" for x in r["upcoming"])


def test_ai_section():
    ctx = bc.prep_context(NOW, _mock_cache())
    ai = ctx["ai"]
    assert ai["five_pct"] == 42 and ai["cx_five_pct"] == 15
    assert ai["cc_tok"] == "1M" or ai["cc_tok"].endswith("M")
    assert ai["custom_total"] == "¥12.34" and ai["custom_name"] == "中转站"
    assert len(ai["chart"]) == 7                            # 近 7 天


def test_device_and_printer():
    ctx = bc.prep_context(NOW, _mock_cache())
    ms = ctx["device"]["machines"]
    assert len(ms) == 1
    nas = ms[0]
    assert nas["name"] == "nas-01"          # 未配置→自动采纳,用 hostname
    assert nas["cpu"] == 23 and nas["mem"] == 50
    assert nas["vols"][0]["name"] == "vol1"
    assert nas["show"]["cpu"] is True       # 无 fields=全显示
    pr = ctx["printer"]
    assert pr is not None and pr["printing"] is True
    assert pr["remaining_text"] == "2小时15分"               # 2.25 小时换算
    assert pr["state_text"] == "打印中"


def test_battery():
    ctx = bc.prep_context(NOW, _mock_cache())
    assert ctx["battery"]["level"] == 87 and ctx["battery"]["has"] is True


def test_empty_cache_degrades_without_error():
    """空 cache 不报错,各段降级。"""
    ctx = bc.prep_context(NOW, {})
    assert ctx["home"]["weather"]["temp"] == "--"
    assert ctx["home"]["reminders"]["total"] == 0
    assert ctx["device"]["machines"] == []
    assert ctx["printer"] is None
    assert ctx["battery"]["has"] is False


def test_device_rename_and_field_filter():
    """配置可重命名设备 + 勾选显示项。"""
    cfg = {"devices": {"machines": [
        {"id": "nas-01", "name": "客厅NAS", "mode": "push", "fields": ["cpu", "mem"]}]}}
    ms = bc.prep_context(NOW, _mock_cache(), cfg)["device"]["machines"]
    nas = next(x for x in ms if x["name"] == "客厅NAS")     # 重命名生效
    assert nas["show"]["cpu"] and nas["show"]["mem"]
    assert not nas["show"]["net"] and not nas["show"]["disk_io"]
    assert nas["vols"] == []                                 # 未勾选任何分区


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} passed")
