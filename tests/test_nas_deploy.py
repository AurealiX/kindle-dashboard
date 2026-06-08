"""Tests for NAS deployment: /api/ccusage endpoint, device persistence, auth exemption."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_ccusage_endpoint_basic():
    """POST /api/ccusage 接收推送并合并。"""
    from fastapi.testclient import TestClient
    from server.app import app, cache, cache_lock

    client = TestClient(app)
    payload = {
        "id": "test-mac-1",
        "cc": {"daily": [{"date": "2026-06-07", "totalTokens": 1000, "totalCost": 5.0}]},
        "codex": {"daily": [{"date": "2026-06-07", "totalTokens": 2000, "totalCost": 10.0}]},
    }
    resp = client.post("/api/ccusage", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["id"] == "test-mac-1"

    with cache_lock:
        assert "ccusage" in cache
        assert cache["ccusage"]["ok"] is True
        merged_cc = cache["ccusage"]["cc"]["daily"]
        assert any(d["totalTokens"] == 1000 for d in merged_cc)


def test_ccusage_endpoint_multi_device_merge():
    """两台设备推送后合并相加。"""
    from fastapi.testclient import TestClient
    from server.app import app, cache, cache_lock

    client = TestClient(app)
    client.post("/api/ccusage", json={
        "id": "dev-A",
        "cc": {"daily": [{"date": "2026-06-07", "totalTokens": 100, "totalCost": 1.0}]},
        "codex": {"daily": []},
    })
    client.post("/api/ccusage", json={
        "id": "dev-B",
        "cc": {"daily": [{"date": "2026-06-07", "totalTokens": 200, "totalCost": 2.0}]},
        "codex": {"daily": []},
    })

    with cache_lock:
        merged = cache["ccusage"]["cc"]["daily"]
        day7 = next((d for d in merged if d["date"] == "2026-06-07"), None)
        assert day7 is not None
        assert day7["totalTokens"] >= 300  # 100 + 200 (may have residual from prior test)


def test_ccusage_endpoint_auth_exempt():
    """/api/ccusage 在鉴权豁免列表里(推送口带不了令牌)。"""
    from server.app import _AUTH_EXEMPT_EXACT
    assert "/api/ccusage" in _AUTH_EXEMPT_EXACT


def test_ccusage_endpoint_device_limit():
    """超过 64 设备上限返回 429。"""
    from fastapi.testclient import TestClient
    from server.app import app, cache, cache_lock

    with cache_lock:
        by_dev = cache.setdefault("ccusage_by_device", {})
        for i in range(64):
            by_dev[f"fake-{i}"] = {"cc": {"daily": []}, "codex": {"daily": []}}

    client = TestClient(app)
    resp = client.post("/api/ccusage", json={
        "id": "one-too-many",
        "cc": {"daily": []},
        "codex": {"daily": []},
    })
    assert resp.status_code == 429

    with cache_lock:
        cache.get("ccusage_by_device", {}).clear()


def test_dockerfile_syntax():
    """Dockerfile 存在且有关键指令。"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "installers", "nas", "Dockerfile")
    assert os.path.exists(path)
    content = open(path).read()
    assert "python:3.12-slim" in content
    assert "chromium" in content
    assert "fonts-noto-cjk" in content
    assert "server.run" in content
    assert "KINDLE_CONFIG=/config/config.yaml" in content
    assert "KINDLE_DATA_DIR=/data" in content


def test_docker_compose_syntax():
    """docker-compose.yml 有必要配置。"""
    import yaml
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "installers", "nas", "docker-compose.yml")
    assert os.path.exists(path)
    with open(path) as f:
        dc = yaml.safe_load(f)
    svc = dc["services"]["kindle-dashboard"]
    assert svc["init"] is True
    assert svc["restart"] == "unless-stopped"
    assert "8585:8585" in svc["ports"]
    assert "config:/config" in svc["volumes"]
    assert "data:/data" in svc["volumes"]
    assert "TZ=Asia/Shanghai" in svc["environment"]


def test_push_ccusage_script_syntax():
    """push_ccusage.sh 语法正确。"""
    import subprocess
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "installers", "macos", "push_ccusage.sh")
    assert os.path.exists(path)
    r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    assert r.returncode == 0, f"Syntax error: {r.stderr}"


def test_enable_ccusage_push_script_syntax():
    """enable_ccusage_push.sh 语法正确。"""
    import subprocess
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "installers", "macos", "enable_ccusage_push.sh")
    assert os.path.exists(path)
    r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    assert r.returncode == 0, f"Syntax error: {r.stderr}"


def test_disable_ccusage_push_script_syntax():
    """disable_ccusage_push.sh 语法正确。"""
    import subprocess
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "installers", "macos", "disable_ccusage_push.sh")
    assert os.path.exists(path)
    r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    assert r.returncode == 0, f"Syntax error: {r.stderr}"


def test_nas_install_script_syntax():
    """installers/nas/install.sh 语法正确。"""
    import subprocess
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "installers", "nas", "install.sh")
    assert os.path.exists(path)
    r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    assert r.returncode == 0, f"Syntax error: {r.stderr}"


def test_enable_reminders_url_param():
    """enable_reminders.sh 支持 --url 参数(bash -n 已验语法)。"""
    import subprocess
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "installers", "macos", "enable_reminders.sh")
    r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    assert r.returncode == 0, f"Syntax error: {r.stderr}"
    content = open(path).read()
    assert "--url" in content
    assert "TARGET_URL" in content


def test_enable_quota_url_param():
    """enable_quota.sh 支持 --url 参数。"""
    import subprocess
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "installers", "macos", "enable_quota.sh")
    r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    assert r.returncode == 0, f"Syntax error: {r.stderr}"
    content = open(path).read()
    assert "--url" in content
    assert "TARGET_URL" in content


if __name__ == "__main__":
    test_ccusage_endpoint_auth_exempt()
    test_dockerfile_syntax()
    test_docker_compose_syntax()
    test_push_ccusage_script_syntax()
    test_enable_ccusage_push_script_syntax()
    test_disable_ccusage_push_script_syntax()
    test_nas_install_script_syntax()
    test_enable_reminders_url_param()
    test_enable_quota_url_param()
    print("All NAS deploy tests passed (non-server tests)!")
