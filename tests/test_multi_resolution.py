"""多分辨率渲染测试:基准画布 + device-scale-factor 等比放大。
覆盖 docs/multi-resolution-spec.md 第 7 节验收标准。
需要 Chrome/Chromium 的用例无则跳过;纯逻辑用例(机型解析)始终跑。
可直接 `python3 tests/test_multi_resolution.py`。
"""
import io
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server.render import styles, pipeline                 # noqa: E402
from server.render.contract import empty_context           # noqa: E402
from server.config.schema import resolve_render_size, KINDLE_MODELS  # noqa: E402

STYLE = "style_a"


def _chrome_or_skip():
    if not pipeline.find_chrome():
        try:
            import pytest
            pytest.skip("无 Chrome/Chromium,跳过渲染")
        except ImportError:
            print("  ⚠ 跳过(无 Chrome)")
            raise SystemExit(0)


# ---- 纯逻辑:机型 → 分辨率解析(不需要 Chrome)----

def test_model_preset_resolves():
    assert resolve_render_size({"kindle_model": "pw5"}) == (1648, 1236)
    assert resolve_render_size({"kindle_model": "base"}) == (800, 600)
    assert resolve_render_size({"kindle_model": "scribe"}) == (2480, 1860)


def test_custom_uses_manual_size():
    cfg = {"kindle_model": "custom", "render_width": 1000, "render_height": 600}
    assert resolve_render_size(cfg) == (1000, 600)


def test_missing_or_bad_falls_back():
    assert resolve_render_size({}) == (800, 600)                       # 老配置无 kindle_model
    assert resolve_render_size({"kindle_model": "???"}) == (800, 600)   # 未知机型
    assert resolve_render_size({"kindle_model": "custom"}) == (800, 600)  # custom 但没填


def test_models_all_landscape_4to3_ish():
    # 基准 4:3;每个预设比例与 4:3 误差应很小(等比放大的前提)
    for v, _label, w, h in KINDLE_MODELS:
        if v == "custom":
            continue
        assert abs(w / h - 800 / 600) < 0.05, f"{v} 比例偏离 4:3 过大"


# ---- 渲染:不同 scale 下产物尺寸正确 ----

def test_default_size_regression():
    """默认 800×600 行为与改动前像素级一致:scale=1,旋转后竖屏 600×800。"""
    _chrome_or_skip()
    rc = pipeline.RenderConfig()   # 默认 base
    png = pipeline.render_html_to_png(styles.render_page(STYLE, "home", empty_context()), rc)
    assert Image.open(io.BytesIO(png)).size == (600, 800)


def test_highres_pw5():
    """PW5 横屏 1648×1236:出图锐利铺满,旋转后竖屏 1236×1648。"""
    _chrome_or_skip()
    rc = pipeline.RenderConfig(width=1648, height=1236)
    rc.rotate = 0
    img = pipeline._shot_to_image(styles.render_page(STYLE, "ai", empty_context()), rc)
    assert img.size == (1648, 1236), f"横屏产物 {img.size}"
    rc.rotate = 270
    png = pipeline.render_html_to_png(styles.render_page(STYLE, "ai", empty_context()), rc)
    assert Image.open(io.BytesIO(png)).size == (1236, 1648), "旋转后竖屏尺寸不对"


def test_non_4to3_letterbox_no_crash():
    """非 4:3(1000×600):等比缩放 + 白底居中,不崩、尺寸精确。"""
    _chrome_or_skip()
    rc = pipeline.RenderConfig(width=1000, height=600)
    rc.rotate = 0
    img = pipeline._shot_to_image(styles.render_page(STYLE, "home", empty_context()), rc)
    assert img.size == (1000, 600), f"letterbox 产物 {img.size}"


if __name__ == "__main__":
    for fn in [test_model_preset_resolves, test_custom_uses_manual_size,
               test_missing_or_bad_falls_back, test_models_all_landscape_4to3_ish,
               test_default_size_regression, test_highres_pw5, test_non_4to3_letterbox_no_crash]:
        fn(); print(f"  ✓ {fn.__name__}")
    print("\nok")
