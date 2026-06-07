"""在线升级模块:版本读取 + 非 git 目录的诚实降级(不依赖网络)。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server import updater          # noqa: E402


def test_version_on_real_repo():
    """本仓库是 git clone,应能读到当前短哈希版本。"""
    assert updater.is_git_repo(ROOT) is True
    v = updater.current_version(ROOT)
    assert v and v != "?" and len(v) >= 4


def test_non_git_dir_degrades_gracefully(tmp_path):
    """非 git 目录:不报错,check/upgrade 都返回失败 + 明确提示(诚实降级)。"""
    d = str(tmp_path)
    assert updater.is_git_repo(d) is False
    assert updater.current_version(d) == "?"
    info = updater.check_for_update(d)
    assert info["ok"] is False and "git" in info["error"]
    ok, msg = updater.do_upgrade(d)
    assert ok is False and "git" in msg


if __name__ == "__main__":
    import tempfile
    test_version_on_real_repo()
    with tempfile.TemporaryDirectory() as d:
        assert updater.is_git_repo(d) is False
        assert updater.check_for_update(d)["ok"] is False
    print("ok")
