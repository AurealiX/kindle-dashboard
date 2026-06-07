"""在线升级:git 拉取最新代码 + 重启服务。

供 macOS 菜单栏「检查更新 / 升级」复用,**不依赖 rumps**(纯 subprocess + git),
所以可在任意平台单元测试。前提:看板是用 `git clone` 安装的(非 git 目录则诚实降级,提示用户)。
配置已外置到仓库外(见 app._resolve_config_path),所以 `git pull` 升级**绝不会动到用户配置**。
"""
import os
import subprocess


def _git(repo, *args, timeout=30):
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True, timeout=timeout)


def is_git_repo(repo):
    try:
        r = _git(repo, "rev-parse", "--is-inside-work-tree")
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


def current_version(repo):
    """当前版本(短哈希);非 git 或失败返回 '?'。"""
    try:
        r = _git(repo, "rev-parse", "--short", "HEAD")
        return r.stdout.strip() or "?" if r.returncode == 0 else "?"
    except Exception:
        return "?"


def check_for_update(repo, branch="main"):
    """联网比对本地与 origin/<branch>。返回:
    {ok: True, current, latest, behind}  或  {ok: False, error}。"""
    if not is_git_repo(repo):
        return {"ok": False, "error": "不是 git 仓库,无法在线升级(请用 git clone 方式安装)。"}
    try:
        f = _git(repo, "fetch", "--quiet", "origin", branch, timeout=40)
    except Exception as e:
        return {"ok": False, "error": f"拉取远程失败:{e}"}
    if f.returncode != 0:
        return {"ok": False, "error": "拉取远程失败(检查网络/代理):" + (f.stderr.strip()[:200])}
    cur = _git(repo, "rev-parse", "HEAD").stdout.strip()
    rem = _git(repo, "rev-parse", f"origin/{branch}").stdout.strip()
    cnt = _git(repo, "rev-list", "--count", f"HEAD..origin/{branch}").stdout.strip()
    try:
        behind = int(cnt)
    except ValueError:
        behind = 0
    return {"ok": True, "current": cur[:7], "latest": rem[:7], "behind": behind}


def do_upgrade(repo, branch="main", restart_script=None):
    """git pull --ff-only,可选地跑重启脚本。返回 (ok: bool, message: str)。
    --ff-only:本地若改过代码导致无法快进,直接报错(不强行合并/丢改动),诚实降级。"""
    if not is_git_repo(repo):
        return False, "不是 git 仓库,无法升级。"
    try:
        p = _git(repo, "pull", "--ff-only", "origin", branch, timeout=180)
    except Exception as e:
        return False, f"升级失败:{e}"
    if p.returncode != 0:
        return False, "升级失败(本地可能改过代码,无法快进):" + (p.stderr.strip()[:200])
    msg = "代码已更新到最新。"
    if restart_script and os.path.exists(restart_script):
        try:
            r = subprocess.run(["bash", restart_script],
                               capture_output=True, text=True, timeout=180)
            msg += "服务已重启。" if r.returncode == 0 else "但重启脚本返回非 0,请手动重启服务。"
        except Exception as e:
            msg += f"但自动重启失败({e}),请手动重启服务。"
    return True, msg
