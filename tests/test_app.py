"""主服务 API 验证(FastAPI TestClient)。用临时 config,不污染仓库;不触发采集/渲染线程。"""
import os
import sys
import json
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# 必须在 import app 前指定临时配置路径(app 模块级初始化 ConfigManager)
TEST_DATA_DIR = tempfile.mkdtemp()
os.environ["KINDLE_CONFIG"] = os.path.join(TEST_DATA_DIR, "config.yaml")
os.environ["KINDLE_DATA_DIR"] = TEST_DATA_DIR

from fastapi.testclient import TestClient  # noqa: E402
from server.app import app, cm              # noqa: E402

client = TestClient(app)                     # 不用 with → 不触发 startup/data_loop


def test_health():
    j = client.get("/health").json()
    assert j["status"] == "ok" and "active_pages" in j


def test_auth_token_protects_management_apis():
    """设了访问令牌:配置/管理接口需令牌;Kindle 拉图、设备上报、health 豁免。"""
    cm.get()["server"]["access_token"] = "T0KEN"   # get() 返回 _config 引用,直接设/清,不走 secret 保留逻辑
    try:
        assert client.get("/api/config").status_code == 401          # 无令牌 → 挡住
        assert client.get("/api/styles").status_code == 401
        assert client.get("/api/config", headers={"X-Access-Token": "T0KEN"}).status_code == 200   # header 令牌
        assert client.get("/api/config?token=T0KEN").status_code == 200                            # query 令牌
        assert client.get("/kindle/frame.png").status_code == 200    # Kindle 拉图豁免
        assert client.get("/health").status_code == 200              # health 豁免
        assert client.post("/api/rate-limits",
                           json={"source": "claude", "rate_limits": {}}).status_code == 200  # 设备上报豁免
    finally:
        cm.get()["server"]["access_token"] = ""    # 清掉,不影响其他测试(空=放行)


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


def test_pull_device_merge_keeps_stale_prune_cleans():
    """⑤:采集(_merge)只更新本轮成功项、**不删旧的**(单台临时失败保留上一帧、不凭空消失);
    改名/删除的清理交给保存时的 _prune_pull_device_cache。push 发现设备始终保留。"""
    from server.app import cache, _merge, _prune_pull_device_cache
    cache["devices_metrics"] = {
        "old-mac": {"hostname": "old-mac", "cpu_pct": 1},
        "push-1": {"hostname": "push-1", "updated_at": 123, "cpu_pct": 2},
    }
    # 这轮只采到 new-mac(old-mac 临时失败、不在本轮结果)→ _merge 不该删 old-mac
    _merge({"devices_metrics": {"new-mac": {"hostname": "new-mac", "cpu_pct": 3}}})
    assert "old-mac" in cache["devices_metrics"]      # 单台失败保留上一帧,不凭空消失
    assert "new-mac" in cache["devices_metrics"]
    assert "push-1" in cache["devices_metrics"]
    # 保存配置(machines 只剩 renamed)→ _prune 剪掉不在配置里的本机/SSH 旧指标,push 保留
    _prune_pull_device_cache({"devices": {"machines": [{"name": "renamed", "mode": "local"}]}})
    assert "old-mac" not in cache["devices_metrics"]
    assert "new-mac" not in cache["devices_metrics"]
    assert "push-1" in cache["devices_metrics"]


def test_apple_sync_buckets_reminders():
    """提醒事项自采自推:POST read_reminders.js 的格式 → build_context 正确分桶。
    覆盖搬运缺口(installers/macos/reminders),防止接收端回归。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from server.app import cache, APPLE_REMINDERS_CACHE, _load_apple_reminders_cache
    from server.render.build_context import prep_context
    # read_reminders.js 产出的字段:title/completed/list/dueDate/priority
    r = client.post("/api/apple-sync", json={
        "updated_at": "2026-06-07T22:00:00Z",
        "reminders": [
            {"title": "过期事", "completed": False, "list": "工作", "dueDate": "2026-06-05T18:00:00Z", "priority": 5},
            {"title": "今天事", "completed": False, "list": "生活", "dueDate": "2026-06-07T10:00:00Z", "priority": 0},
            {"title": "明天事", "completed": False, "list": "待办", "dueDate": "2026-06-08T09:00:00Z", "priority": 1},
            {"title": "已完成", "completed": True,  "list": "待办", "dueDate": None, "priority": 0},
        ],
    })
    assert r.json()["status"] == "ok"
    assert cache.get("reminders")  # 接收端已存
    persisted = json.load(open(APPLE_REMINDERS_CACHE, encoding="utf-8"))
    assert persisted["reminders"][0]["title"] == "过期事"
    cache.pop("reminders", None)
    cache.pop("apple_updated", None)
    _load_apple_reminders_cache()
    assert cache.get("reminders") and cache.get("apple_updated") == "2026-06-07T22:00:00Z"
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


def test_printers_endpoint_requires_saved_ha():
    """打印机扫描需先配 HA 地址+令牌;空配置 → 400 + 明确提示(不打网络)。"""
    r = client.get("/api/printers")
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
    assert client.get("/agent/install.ps1").status_code == 200          # Windows
    assert client.get("/agent/push_agent.ps1").status_code == 200
    assert client.get("/agent/collect_windows.ps1").status_code == 200
    assert client.get("/agent/evil.sh").status_code == 404
    assert client.get("/agent/../config.yaml").status_code == 404   # 不许穿越白名单


def test_server_url_replaces_loopback_for_agent_commands():
    """设置页从 127.0.0.1 打开时,远程 agent 命令应使用 LAN 地址。"""
    import server.app as appmod
    old = appmod._lan_ips
    appmod._lan_ips = lambda: ["192.168.1.20", "10.0.0.8"]
    try:
        j = client.get("/api/server-url", headers={"host": "127.0.0.1:8585"}).json()
    finally:
        appmod._lan_ips = old
    assert j["is_loopback"] is True
    assert j["recommended"] == "http://192.168.1.20:8585"
    assert "http://192.168.1.20:8585" in j["candidates"]


def test_lan_priority_demotes_proxy_tun():
    """开着代理(Clash 的 198.18.0.1 TUN)时,真实 LAN 段应排前,虚拟网卡垫底。
    防回归:_lan_ips 的 recommended=ips[0] 不能选中 198.18.x。"""
    import server.app as appmod
    # socket 探测常把代理 TUN 放第一位,排序后必须被挤到最后
    got = sorted(["198.18.0.1", "192.168.5.19", "10.0.0.8", "172.20.1.2"],
                 key=appmod._lan_priority)
    assert got[0] == "192.168.5.19"        # 192.168 段最优先
    assert got[-1] == "198.18.0.1"         # 代理 TUN 垫底
    assert appmod._lan_priority("198.18.0.1") > appmod._lan_priority("10.0.0.8")


def test_config_path_external_with_auto_migration(tmp_path):
    """配置外置:KINDLE_CONFIG 覆盖优先;新位置缺、旧仓库内有 → 自动迁移搬出来。"""
    import server.app as appmod
    # 1) 环境变量覆盖,直接用
    assert appmod._resolve_config_path(env="/custom/c.yaml") == "/custom/c.yaml"
    old = tmp_path / "repo" / "config.yaml"
    old.parent.mkdir()
    old.write_text("server: {port: 9}\n", encoding="utf-8")
    # 2) 新位置不存在 + 旧存在 → 迁移(连同建目录),返回新路径且内容搬过去
    new = tmp_path / "ext" / "kindle-dashboard" / "config.yaml"
    got = appmod._resolve_config_path(env="", new_default=str(new), old_default=str(old))
    assert got == str(new)
    assert new.read_text(encoding="utf-8") == "server: {port: 9}\n"
    # 3) 新位置已存在 → 不迁移、不覆盖
    new2 = tmp_path / "ext2.yaml"
    new2.write_text("keep: me\n", encoding="utf-8")
    assert appmod._resolve_config_path(env="", new_default=str(new2), old_default=str(old)) == str(new2)
    assert new2.read_text(encoding="utf-8") == "keep: me\n"
    # 4) 新旧都没有 → 返回新路径(不报错,服务后续全默认)
    none_old = tmp_path / "nope.yaml"
    new3 = tmp_path / "ext3.yaml"
    assert appmod._resolve_config_path(env="", new_default=str(new3), old_default=str(none_old)) == str(new3)


def test_server_url_includes_local_mdns_candidate():
    """.local mDNS 候选:支持 mDNS 的设备(Mac/Linux/手机)可选它当看板地址,绕开 IP 漂移;
    出现在 candidates 供设置页 agent 命令下拉选,但**不抢 recommended**(默认仍用 IP,兼容不支持 mDNS 的设备)。"""
    import server.app as appmod
    old = appmod._local_hostname_url
    appmod._local_hostname_url = lambda scheme, port: f"{scheme}://mymac.local:{port}"
    try:
        j = client.get("/api/server-url", headers={"host": "127.0.0.1:8585"}).json()
    finally:
        appmod._local_hostname_url = old
    assert "http://mymac.local:8585" in j["candidates"]
    assert j["recommended"] != "http://mymac.local:8585"


def test_styles_endpoint():
    j = client.get("/api/styles").json()
    assert "style_a" in j["styles"] and "home" in j["pages"]


def test_setup_page_served():
    r = client.get("/setup")
    assert r.status_code == 200 and "实时预览" in r.text and "/api/server-url" in r.text


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} passed")
