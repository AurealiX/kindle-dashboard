"""i18n(中英双语)测试。

覆盖 docs/i18n-spec.md 验收点:
- schema.to_json('en') 给英文 label/help(缺则回退中文);默认 zh 与无参一致(回归)。
- server.language 字段存在且默认 zh。
- build_context lang='en':隐藏中国元素(农历/干支/节气/日历副文本),星期/打印机/倒计时/提醒标签英文化。
- render_page 按 lang 注入各风格 t(en 缺条目回退 zh);zh 渲染。
渲染相关用例需 Chrome,无则跳过。可直接 `python3 tests/test_i18n.py`。
"""
import io
import os
import sys
import json
import copy

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from server.config import schema                              # noqa: E402
from server.render import styles, pipeline                    # noqa: E402
from server.render.build_context import prep_context          # noqa: E402
from server.render.contract import empty_context, PAGES       # noqa: E402
import preview_style as ps                                    # noqa: E402


def _chrome_or_skip():
    if not pipeline.find_chrome():
        try:
            import pytest
            pytest.skip("无 Chrome/Chromium")
        except ImportError:
            print("  ⚠ 跳过(无 Chrome)"); raise SystemExit(0)


# ---------- schema 双语 ----------

def test_language_field_exists_default_zh():
    cfg = schema.default_config()
    assert cfg["server"]["language"] == "zh"
    srv = next(s for s in schema.SCHEMA if s.key == "server")
    f = next(f for f in srv.fields if f.key == "language")
    assert f.type == "enum" and [o[0] for o in f.options] == ["zh", "en"]


def test_to_json_zh_unchanged():
    """zh(默认)输出与无参完全一致 —— 回归底线。"""
    assert json.dumps(schema.to_json("zh"), ensure_ascii=False) == \
           json.dumps(schema.to_json(), ensure_ascii=False)


def test_to_json_en_translates_with_fallback():
    en = schema.to_json("en")
    srv = next(s for s in en if s["key"] == "server")
    assert srv["label"] == "Server"                       # section label_en
    port = next(f for f in srv["fields"] if f["key"] == "port")
    assert port["label"] == "Port"                        # field label_en
    tz = next(f for f in srv["fields"] if f["key"] == "timezone")
    # timezone 无 help_en → 回退中文 help(可能为空字符串),不报错即可
    assert isinstance(tz["help"], str)
    # enum option 英文化(devices.mode local→英文)
    dev = next(s for s in en if s["key"] == "devices")
    mlist = next(f for f in dev["fields"] if f["key"] == "machines")
    mode = next(f for f in mlist["item_fields"] if f["key"] == "mode")
    labels = [o[1] for o in mode["options"]]
    assert any("Local" in x for x in labels)


# ---------- build_context 双语 ----------

def _ctx(lang):
    cfg = copy.deepcopy(ps.MOCK_CFG)
    cfg.setdefault("server", {})["language"] = lang
    return prep_context(ps.NOW, ps.mock_cache(), cfg)


def test_zh_keeps_china_elements():
    c = _ctx("zh")["home"]
    assert c["lunar"] and c["ganzhi"] and c["term"]       # 非空
    assert c["weekday"] in ["周一","周二","周三","周四","周五","周六","周日"]


def test_en_hides_china_elements():
    c = _ctx("en")["home"]
    assert c["lunar"] == "" and c["ganzhi"] == "" and c["term"] == ""
    assert c["weekday"] in ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    # 日历格子副文本与节日标注在英文版清空
    cells = [x for w in c["calendar"] for x in w if x]
    assert cells and all(x["l"] == "" and not x["holiday"] for x in cells)


def test_en_localizes_dynamic_strings():
    ai = _ctx("en")["ai"]
    assert "in " in ai["five_reset"] or ai["five_reset"] == "soon"
    pr = _ctx("en")["printer"]
    assert pr["state_text"] == "Printing" and pr["speed"] == "Standard"
    assert "h " in pr["remaining_text"] or "m" in pr["remaining_text"]
    # 风向后缀「级」英文版去掉
    assert "级" not in _ctx("en")["home"]["weather"]["wind"]


def test_lang_in_ctx_and_empty_context():
    assert _ctx("en")["lang"] == "en"
    assert empty_context()["lang"] == "zh"


# ---------- render_page 注入 t ----------

def test_render_injects_style_strings():
    """每套风格都有 strings.json,且 zh/en 都能渲染出 HTML(不抛错)。"""
    ctx_zh = empty_context()
    ctx_en = dict(empty_context()); ctx_en["lang"] = "en"
    for style in styles.list_styles():
        # 每套都应带 strings.json(i18n 已铺全)
        st = styles.read_strings(style)
        assert st.get("zh"), f"{style} 缺 strings.json zh"
        for page in PAGES:
            if not styles.has_page(style, page):
                continue
            assert styles.render_page(style, page, ctx_zh)   # zh 不抛错
            assert styles.render_page(style, page, ctx_en)   # en 不抛错(缺键回退 zh)


def test_en_render_no_china_calendar_leak():
    """英文渲染:看板正文(去 <style>)不含农历/干支/节气/中文星期。需 Chrome 才出图,但 HTML 检查不需要。"""
    ctx = _ctx("en")
    ctx["ha"] = {"cards": []}
    ban = ["农历","干支","节气","初一","廿","周一","周二","周三","周四","周五","周六","周日"]
    bad = []
    for style in styles.list_styles():
        for page in PAGES:
            if not styles.has_page(style, page):
                continue
            body = styles.render_page(style, page, ctx).split("</style>", 1)[-1]
            hit = [b for b in ban if b in body]
            if hit:
                bad.append(f"{style}/{page}:{hit}")
    assert not bad, "英文正文残留中国元素/中文星期:\n" + "\n".join(bad)


if __name__ == "__main__":
    for fn in [test_language_field_exists_default_zh, test_to_json_zh_unchanged,
               test_to_json_en_translates_with_fallback, test_zh_keeps_china_elements,
               test_en_hides_china_elements, test_en_localizes_dynamic_strings,
               test_lang_in_ctx_and_empty_context, test_render_injects_style_strings,
               test_en_render_no_china_calendar_leak]:
        fn(); print(f"  ✓ {fn.__name__}")
    print("\nok")
