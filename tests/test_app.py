"""主服务 API 验证(FastAPI TestClient)。用临时 config,不污染仓库;不触发采集/渲染线程。"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# 必须在 import app 前指定临时配置路径(app 模块级初始化 ConfigManager)
os.environ["KINDLE_CONFIG"] = os.path.join(tempfile.mkdtemp(), "config.yaml")

from fastapi.testclient import TestClient  # noqa: E402
from server.app import app                  # noqa: E402

client = TestClient(app)                     # 不用 with → 不触发 startup/data_loop


def test_health():
    j = client.get("/health").json()
    assert j["status"] == "ok" and "active_pages" in j


def test_schema_served():
    j = client.get("/api/schema").json()
    assert isinstance(j, list) and any(s["key"] == "weather" for s in j)


def test_get_config_has_status():
    j = client.get("/api/config").json()
    assert "config" in j and "status" in j


def test_save_config_and_redact():
    r = client.post("/api/config", json={"config": {"weather": {"key": "sk-real", "location": "101010100"}}})
    assert r.json()["ok"] is True
    j = client.get("/api/config").json()
    assert j["config"]["weather"]["key"] == "••••••"     # 脱敏不吐真实值
    assert "home" in j["status"]["active_pages"]          # 配置即页面


def test_save_invalid_rejected():
    r = client.post("/api/config", json={"config": {"home_assistant": {"url": "http://x:8123"}}})
    assert r.status_code == 400 and r.json()["ok"] is False
    assert any("令牌" in e for e in r.json()["errors"])


def test_device_push_and_discover():
    r = client.post("/api/device-metrics", json={
        "id": "pc-1", "hostname": "my-pc",
        "metrics": {"cpu_pct": 50, "mem_used": 1, "mem_total": 2,
                    "disks": [{"name": "C:", "pct": 40, "used": 1, "total": 2}]}})
    assert r.json()["status"] == "ok"
    devs = client.get("/api/discovered-devices").json()["devices"]
    pc = next((x for x in devs if x["key"] == "pc-1"), None)
    assert pc is not None and pc["hostname"] == "my-pc"
    assert "cpu" in pc["fields"] and "vol:C:" in pc["fields"]  # 动态字段含分区


def test_apple_sync_buckets_reminders():
    """提醒事项自采自推:POST read_reminders.js 的格式 → build_context 正确分桶。
    覆盖搬运缺口(installers/macos/reminders),防止接收端回归。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from server.app import cache
    from server.render.build_context import prep_context
    # read_reminders.js 产出的字段:title/completed/list/dueDate/priority
    r = client.post("/api/apple-sync", json={
        "updated_at": "2026-06-07T22:00:00Z",
        "reminders": [
            {"title": "过期事", "completed": False, "list": "工作", "dueDate": "2026-06-06T18:00:00Z", "priority": 5},
            {"title": "今天事", "completed": False, "list": "生活", "dueDate": "2026-06-07T10:00:00Z", "priority": 0},
            {"title": "明天事", "completed": False, "list": "待办", "dueDate": "2026-06-08T09:00:00Z", "priority": 1},
            {"title": "已完成", "completed": True,  "list": "待办", "dueDate": None, "priority": 0},
        ],
    })
    assert r.json()["status"] == "ok"
    assert cache.get("reminders")  # 接收端已存
    now = datetime(2026, 6, 7, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    rem = prep_context(now, dict(cache), {})["home"]["reminders"]
    assert rem["total"] == 3                                   # 已完成被过滤
    assert [x["title"] for x in rem["overdue"]] == ["过期事"]
    assert [x["title"] for x in rem["today"]] == ["今天事"]
    assert any(x["title"] == "明天事" and x["dt"] == "明天" for x in rem["upcoming"])


def test_city_search_requires_saved_key():
    """城市搜索需先配天气 host/key;测试用空配置 → 400 + 明确提示(不打网络)。"""
    r = client.get("/api/city-search?q=上海")
    assert r.status_code == 400
    j = r.json()
    assert j["ok"] is False and "key" in j["error"].lower() or "Key" in j["error"]


def test_schema_location_is_city_with_hidden_name():
    """location 改为 city 类型(城市选择器);location_name 隐藏(由选择器写入)。"""
    schema_json = client.get("/api/schema").json()
    w = next(s for s in schema_json if s["key"] == "weather")
    loc = next(f for f in w["fields"] if f["key"] == "location")
    name = next(f for f in w["fields"] if f["key"] == "location_name")
    assert loc["type"] == "city"
    assert name["hidden"] is True


def test_ha_entities_requires_saved_ha():
    """实体搜索需先配 HA 地址+令牌;空配置 → 400 + 明确提示(不打网络)。"""
    r = client.get("/api/ha-entities?q=客厅")
    assert r.status_code == 400
    j = r.json()
    assert j["ok"] is False and "Home Assistant" in j["error"]


def test_interval_resolution():
    """间隔解析(新签名:段+字段+默认):自定义生效、缺失/非法/0 回落默认、最低 5 秒。"""
    from server.app import _interval
    assert _interval({"weather": {"interval": 900}}, "weather", "interval", 600) == 900
    assert _interval({}, "weather", "interval", 600) == 600                          # 默认
    assert _interval({"weather": {"interval": "x"}}, "weather", "interval", 600) == 600   # 非法
    assert _interval({"weather": {"interval": 0}}, "weather", "interval", 600) == 600     # 0=默认
    assert _interval({"server": {"render_interval": 2}}, "server", "render_interval", 30) == 5  # 下限


def test_interval_fields_per_card():
    """间隔分散到各源卡:独立 intervals 段已删;各源段含 interval 字段。"""
    schema_json = client.get("/api/schema").json()
    assert "intervals" not in {s["key"] for s in schema_json}     # 独立段已删
    def has(sec, field):
        s = next(x for x in schema_json if x["key"] == sec)
        return any(f["key"] == field for f in s["fields"])
    assert has("weather", "interval") and has("ai_usage", "interval")
    assert has("home_assistant", "interval") and has("devices", "interval")
    assert has("mstodo", "interval") and has("reminders", "interval")
    assert has("server", "render_interval")
    assert has("ai_usage", "codex_quota_interval") and has("ai_usage", "claude_quota_interval")


def test_agent_files_served():
    """推送 agent 脚本下发:白名单内 200 且是脚本内容,白名单外 404(防任意文件读取)。"""
    r = client.get("/agent/install.sh")
    assert r.status_code == 200 and "kindle-dash-agent" in r.text
    assert client.get("/agent/push_agent.sh").status_code == 200
    assert client.get("/agent/collect_linux.sh").status_code == 200
    assert client.get("/agent/collect_macos.sh").status_code == 200
    assert client.get("/agent/evil.sh").status_code == 404
    assert client.get("/agent/../config.yaml").status_code == 404   # 不许穿越白名单


def test_styles_endpoint():
    j = client.get("/api/styles").json()
    assert "style_a" in j["styles"] and "home" in j["pages"]


def test_setup_page_served():
    r = client.get("/setup")
    assert r.status_code == 200 and "实时预览" in r.text


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} passed")
