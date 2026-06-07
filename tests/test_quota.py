"""AI 额度(Claude statusLine + Codex wham)采集/上报测试。

额度走 push:设备上采集 → POST /api/rate-limits(接收端/契约/展示已就位,见 build_context)。
- Claude:claude_statusline.py 读 Claude Code 喂的 stdin JSON 的 rate_limits → 存本地 + POST(source=claude)
- Codex:codex_quota.py 调 wham/usage → sync_codex_quota.sh 转格式 → POST(source=codex)

这里验 Linux 上可验的部分:Claude 解析/输出/本地缓存、Codex 同步的格式转换+POST payload、
enable_quota 写 quota.conf、全脚本语法。launchd/statusLine 真装与 wham 真实调用只能 Mac 真机验。
"""
import os
import sys
import json
import shutil
import subprocess
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDIR = os.path.join(REPO, "installers/macos/quota")
CLAUDE_SL = os.path.join(QDIR, "claude_statusline.py")
CODEX_Q = os.path.join(QDIR, "codex_quota.py")
SYNC = os.path.join(QDIR, "sync_codex_quota.sh")
ENABLE = os.path.join(REPO, "installers/macos/enable_quota.sh")
DISABLE = os.path.join(REPO, "installers/macos/disable_quota.sh")


def test_claude_statusline_parses_outputs_and_caches(tmp_path):
    """喂 Claude Code 风格的 stdin JSON,应输出含 5h/周% 的状态栏,并写本地 rate-limits.json。"""
    (tmp_path / ".claude").mkdir()
    env = dict(os.environ, HOME=str(tmp_path),
               KINDLE_RATELIMIT_URL="http://127.0.0.1:9/api/rate-limits",  # 无效端口,POST 被吞
               KINDLE_QUOTA_PUSH_INTERVAL="300")
    stdin = json.dumps({
        "context_window": {"used_percentage": 30, "total_input_tokens": 1000,
                           "total_output_tokens": 500, "context_window_size": 200000},
        "rate_limits": {"five_hour": {"used_percentage": 62, "resets_at": 9999999999},
                        "seven_day": {"used_percentage": 51, "resets_at": 9999999999}},
    })
    r = subprocess.run([sys.executable, CLAUDE_SL], input=stdin, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "62%" in r.stdout and "51%" in r.stdout   # 5h / 周额度都显示了
    cache = json.load(open(tmp_path / ".claude" / "rate-limits.json"))
    assert cache["rate_limits"]["five_hour"]["used_percentage"] == 62


def test_claude_statusline_degrades_on_empty_stdin(tmp_path):
    """空输入不崩(诚实降级)。"""
    env = dict(os.environ, HOME=str(tmp_path))
    r = subprocess.run([sys.executable, CLAUDE_SL], input="", env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0


def test_sync_codex_transforms_and_posts(tmp_path):
    """sync 应把 codex_quota.py 的 primary/secondary 转成看板契约并 POST(source=codex)。"""
    qdir = tmp_path / "quota"
    qdir.mkdir()
    # 假 codex_quota.py:输出固定额度
    (qdir / "codex_quota.py").write_text(
        "print('{\"primary\":{\"usedPercent\":62,\"resetsAt\":111},"
        "\"secondary\":{\"usedPercent\":51,\"resetsAt\":222}}')\n")
    shutil.copy(SYNC, qdir / "sync_codex_quota.sh")
    # 假 curl:把 -d 的 payload dump 到文件
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "curl").write_text(
        "#!/bin/sh\nwhile [ $# -gt 0 ]; do "
        "if [ \"$1\" = \"-d\" ]; then printf '%s' \"$2\" > \"$CURL_DUMP\"; fi; shift; done\nexit 0\n")
    os.chmod(bindir / "curl", 0o755)
    dump = tmp_path / "payload.json"
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}",
               CURL_DUMP=str(dump), KINDLE_PY=sys.executable,
               KINDLE_RATELIMIT_URL="http://x/api/rate-limits")
    r = subprocess.run(["bash", str(qdir / "sync_codex_quota.sh")], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    payload = json.load(open(dump))
    assert payload["source"] == "codex"
    assert payload["rate_limits"]["five_hour"]["used_percentage"] == 62
    assert payload["rate_limits"]["seven_day"]["resets_at"] == 222


def test_codex_quota_degrades_without_auth(tmp_path):
    """没有 ~/.codex/auth.json 时输出 error JSON、非零退出,不抛栈。"""
    env = dict(os.environ, HOME=str(tmp_path))   # 空 HOME → 无 auth.json
    r = subprocess.run([sys.executable, CODEX_Q], env=env, capture_output=True, text=True)
    out = json.loads(r.stdout)
    assert "error" in out


def test_enable_quota_writes_conf(tmp_path):
    """KINDLE_SKIP_AGENT=1:跳过 launchd/statusLine,但应写 conf 并打开 AI 页。"""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump(
        {"server": {"port": 8585}, "ai_usage": {"codex_quota_interval": 600, "claude_quota_interval": 300}},
        allow_unicode=True))
    env = dict(os.environ, KINDLE_SKIP_AGENT="1", KINDLE_CONFIG=str(cfg))
    r = subprocess.run(["bash", ENABLE], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    conf = open(os.path.join(QDIR, "quota.conf"), encoding="utf-8").read()
    assert "KINDLE_RATELIMIT_URL=http://127.0.0.1:8585/api/rate-limits" in conf
    assert "KINDLE_QUOTA_PUSH_INTERVAL=300" in conf
    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert saved["ai_usage"]["enabled"] is True


def test_disable_quota_runs(tmp_path):
    """非 Mac 也应优雅退出(无 launchctl 跳过)。"""
    r = subprocess.run(["bash", DISABLE], env=dict(os.environ, HOME=str(tmp_path)),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_scripts_syntax_ok():
    for sh in (SYNC, ENABLE, DISABLE):
        r = subprocess.run(["bash", "-n", sh], capture_output=True, text=True)
        assert r.returncode == 0, f"{sh}: {r.stderr}"
    for py in (CLAUDE_SL, CODEX_Q):
        r = subprocess.run([sys.executable, "-m", "py_compile", py], capture_output=True, text=True)
        assert r.returncode == 0, f"{py}: {r.stderr}"
