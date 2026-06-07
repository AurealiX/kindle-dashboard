"""风格预览工具:把指定风格的所有页渲染成 PNG(横屏正立,用 mock 数据)。

风格作者迭代必备 —— 不用起服务,一条命令看到 5 页在真实数据下的样子。
用法:
    python3 scripts/preview_style.py <风格名>          # 真实 mock 数据
    python3 scripts/preview_style.py <风格名> --empty   # 空数据(验证降级不报错)
输出:/tmp/preview_<风格>_<页>.png
"""
import io
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image  # noqa: E402
from server.render import styles, pipeline  # noqa: E402
from server.render.build_context import prep_context  # noqa: E402
from server.render.contract import empty_context, PAGES  # noqa: E402

NOW = datetime(2026, 6, 7, 14, 30, 5)


def mock_cache():
    import time
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
        ],
        "ccusage": {"ok": True,
                    "cc": {"daily": [{"date": d, "totalTokens": 1_200_000 - i * 90000, "totalCost": 8.1}
                                     for i, d in enumerate([f"2026-06-{x:02d}" for x in range(1, 8)])]},
                    "codex": {"daily": [{"date": f"2026-06-0{x}", "totalTokens": 600_000, "costUSD": 4.2}
                                        for x in range(1, 8)]}},
        "rate_limits": {"five_hour": {"used_percentage": 42, "resets_at": soon},
                        "seven_day": {"used_percentage": 30, "resets_at": soon}},
        "codex_rate_limits": {"five_hour": {"used_percentage": 15, "resets_at": soon},
                              "seven_day": {"used_percentage": 10, "resets_at": soon}},
        "devices_metrics": {
            "nas": {"hostname": "nas", "cpu_pct": 23, "mem_used": 8 * 1024**3, "mem_total": 16 * 1024**3,
                    "net_rx": 1_200_000, "net_tx": 300_000, "disk_read": 0, "disk_write": 500_000,
                    "disks": [{"name": "系统", "pct": 14, "used": 13 * 1024**3, "total": 67 * 1024**3},
                              {"name": "存储池", "pct": 61, "used": 600 * 1024**3, "total": 1024**4}]},
            "mac": {"hostname": "mac", "cpu_pct": 8, "mem_used": 9 * 1024**3, "mem_total": 16 * 1024**3,
                    "net_rx": 50_000, "net_tx": 20_000, "disk_read": 0, "disk_write": 0, "disks": []},
        },
        "printer": {"online": True, "status": "running", "progress": 47,
                    "task": "benchy_v3.3mf", "layer": "120", "total_layer": "256",
                    "remaining_min": 2.25, "nozzle": "210", "nozzle_t": "210",
                    "bed": "60", "bed_t": "60", "speed": "standard",
                    "weight": "15", "material": "PLA", "cooling_fan": "100", "printer_name": "A1"},
        "kindle_battery": 87, "kindle_charging": False,
    }


MOCK_CFG = {
    "devices": {"machines": [
        {"name": "客厅NAS", "id": "nas", "mode": "push"},
        {"name": "我的Mac", "id": "mac", "mode": "local"},
    ]},
    "ai_usage": {"claude_rate": 0.5, "codex_rate": 0.1},   # 演示自定义价倍率
}


def main():
    if len(sys.argv) < 2:
        print(f"用法: python3 scripts/preview_style.py <风格名> [--empty]")
        print(f"可用风格: {styles.list_styles()}")
        sys.exit(1)
    style = sys.argv[1]
    use_empty = "--empty" in sys.argv
    if style not in styles.list_styles():
        print(f"✗ 风格 '{style}' 不存在。可用: {styles.list_styles()}")
        sys.exit(1)

    ctx = empty_context() if use_empty else prep_context(NOW, mock_cache(), MOCK_CFG)
    rc = pipeline.RenderConfig.from_config({})
    rc.rotate = 0   # 横屏正立(电脑上看)
    print(f"风格 {style}{'(空数据)' if use_empty else ''}:")
    for page in PAGES:
        if not styles.has_page(style, page):
            print(f"  - {page}: (该风格无此页模板)")
            continue
        try:
            png = pipeline.render_html_to_png(styles.render_page(style, page, ctx), rc)
            out = f"/tmp/preview_{style}_{page}.png"
            with open(out, "wb") as f:
                f.write(png)
            sz = Image.open(io.BytesIO(png)).size
            print(f"  ✓ {page}: {out}  {sz}")
        except Exception as e:
            print(f"  ✗ {page}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
