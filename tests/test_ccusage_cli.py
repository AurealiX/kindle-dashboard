"""本地 ccusage 采集器验证。真实采集需本机装 ccusage,无则跳过。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server.sources import ccusage_cli  # noqa: E402


def test_disabled_returns_none():
    assert ccusage_cli.collect({"ai_usage": {"enabled": False}}) is None


def test_cmd_includes_timezone():
    """命令必带 --timezone(CLAUDE.md 坑:否则按本机时区切天,跨时区错位)。"""
    cmd = ccusage_cli._cmd("/x/ccusage", "claude", "Asia/Shanghai")
    assert cmd[:4] == ["/x/ccusage", "claude", "daily", "--json"]
    assert "--timezone" in cmd and "Asia/Shanghai" in cmd


def test_persist_save_load_and_replay():
    """落盘+回放:成功采集落盘;ccusage 不可用/没采到时 collect 回放上次;禁用则不回放。"""
    import tempfile
    orig_p, orig_bin = ccusage_cli._PERSIST, ccusage_cli._bin
    ccusage_cli._PERSIST = os.path.join(tempfile.mkdtemp(), "cc.json")
    try:
        frag = {"ccusage": {"ok": True,
                            "cc": {"daily": [{"date": "2026-06-07", "totalTokens": 100, "totalCost": 1.0}]},
                            "codex": {"daily": []}}}
        ccusage_cli._save(frag)
        assert ccusage_cli._load() == frag                     # 存得回、读得出
        ccusage_cli._bin = lambda: ""                          # ccusage 不可用
        assert ccusage_cli.collect({"ai_usage": {"enabled": True}}) == frag   # 回放上次
        assert ccusage_cli.collect({"ai_usage": {"enabled": False}}) is None  # 禁用不回放
    finally:
        ccusage_cli._PERSIST, ccusage_cli._bin = orig_p, orig_bin


def test_local_collect_shape():
    """本机有 ccusage 时,返回结构符合看板契约(cc/codex daily)。"""
    if not ccusage_cli._bin():
        try:
            import pytest
            pytest.skip("本机无 ccusage,跳过")
        except ImportError:
            print("  ⚠ 跳过:无 ccusage")
            raise SystemExit(0)
    frag = ccusage_cli.collect({"ai_usage": {"enabled": True}})
    if frag:  # 有 ccusage 且有日志数据
        cu = frag["ccusage"]
        assert cu["ok"] is True
        assert "daily" in cu["cc"] and "daily" in cu["codex"]
        for row in cu["cc"]["daily"][:1]:
            assert "date" in row and "totalTokens" in row


def test_codex_disabled_skips_codex_run():
    """codex_enabled=False → 不调 ccusage codex(省每轮 ~10s 日志解析)。"""
    import tempfile
    orig_p, orig_bin, orig_daily = ccusage_cli._PERSIST, ccusage_cli._bin, ccusage_cli._daily
    ccusage_cli._PERSIST = os.path.join(tempfile.mkdtemp(), "cc.json")
    calls = []

    def fake_daily(binp, agent, tz):
        calls.append(agent)
        return [{"date": "2026-06-07", "totalTokens": 1, "totalCost": 0.1}]

    try:
        ccusage_cli._bin = lambda: "/x/ccusage"
        ccusage_cli._daily = fake_daily
        frag = ccusage_cli.collect({"ai_usage": {"enabled": True, "codex_enabled": False}})
        assert calls == ["claude"]                      # codex 没被调
        assert frag["ccusage"]["codex"]["daily"] == []  # codex 留空
        calls.clear()
        ccusage_cli.collect({"ai_usage": {"enabled": True}})   # 默认仍跑两个
        assert calls == ["claude", "codex"]
    finally:
        ccusage_cli._PERSIST, ccusage_cli._bin, ccusage_cli._daily = orig_p, orig_bin, orig_daily


def test_codex_off_templates_hide_codex_all_styles():
    """全部 7 套风格的 ai 页:codex_on 两个分支都能渲染(纯 Jinja,无需 Chrome);
    codex_on=False 时页面不再出现 Codex 字样。"""
    from server.render import styles, contract
    import glob as _glob
    style_dirs = [os.path.basename(p) for p in _glob.glob(os.path.join(ROOT, "styles", "*"))
                  if os.path.isdir(p)]
    assert len(style_dirs) >= 7
    for s in style_dirs:
        for flag in (True, False):
            ctx = contract.empty_context()
            ctx["ai"]["codex_on"] = flag
            html = styles.render_page(s, "ai", ctx)
            has_codex = ("Codex" in html) or ("CODEX" in html)
            if flag:
                assert has_codex, f"{s}: codex_on=True 应显示 Codex"
            else:
                assert not has_codex, f"{s}: codex_on=False 仍出现 Codex 字样"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} passed")
