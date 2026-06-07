"""设备监控分发器验证。本机直读在 Linux 环境可端到端跑;Mac/Win 真机另测。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server.sources import metrics  # noqa: E402


def test_detect_platform():
    assert metrics.detect_local_platform() in ("linux", "macos", "windows")


def test_read_local():
    """本机直读返回合理指标(此环境为 Linux)。"""
    plat = metrics.detect_local_platform()
    m = metrics.read_local(plat)
    assert 0 <= m["cpu_pct"] <= 100
    assert m["mem_total"] > 0 and 0 < m["mem_used"] <= m["mem_total"]
    assert isinstance(m["disks"], list)
    for k in ("net_rx", "net_tx", "disk_read", "disk_write"):
        assert m[k] >= 0


def test_collect_local_machine():
    """collect 端到端:配置一台 local 机器 → devices_metrics 含它。"""
    plat = metrics.detect_local_platform()
    cfg = {"devices": {"machines": [{"name": "本机", "mode": "local", "platform": plat}]}}
    frag = metrics.collect(cfg)
    assert frag and "本机" in frag["devices_metrics"]
    assert frag["devices_metrics"]["本机"]["mem_total"] > 0


def test_collect_skips_push():
    """push 机器不在 collect 里采集(由 API 接收)。"""
    cfg = {"devices": {"machines": [{"name": "远端", "mode": "push", "platform": "linux"}]}}
    assert metrics.collect(cfg) is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} passed")
