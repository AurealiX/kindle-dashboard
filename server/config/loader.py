"""配置加载 / 校验 / 热重载 / 保存。

启动读 config.yaml(没有就用全默认,服务照样起、全降级);设置网页保存即写文件、
下一轮渲染热重载生效,不重启(对应 CLAUDE.md「配置即页面」「热重载」)。

凭据安全:
- 给前端的配置经 redacted() 脱敏,secret 字段已填的回显为掩码、不吐真实值。
- 保存时 secret 字段提交掩码/空串 = 视为"不修改",保留原值(防脱敏回显把密钥清空)。
- 写盘原子(.tmp → os.replace),避免半截文件。
"""
import os
import threading

import yaml

from server.config import schema

SECRET_MASK = "••••••"


def _deep_fill(default: dict, loaded: dict) -> dict:
    """以 default 为底,用 loaded 覆盖;loaded 缺的项用 default 补全。"""
    out = {}
    for sec in schema.SCHEMA:
        d = dict(default.get(sec.key, {}))
        l = (loaded or {}).get(sec.key, {}) or {}
        for f in sec.fields:
            if f.type == "module_list":
                items = l.get(f.key, d.get(f.key, [])) or []
                out_items = []
                for item in items:
                    filled = {}
                    for sub in (f.item_fields or []):
                        filled[sub.key] = item.get(sub.key, "" if sub.secret else sub.default)
                    out_items.append(filled)
                d[f.key] = out_items
            elif f.key in l:
                d[f.key] = l[f.key]
        out[sec.key] = d
    return out


class ConfigManager:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._config = schema.default_config()
        self._errors = []
        self._mtime = None
        self._exists = False
        self.load()

    # ---- 读 ----
    def load(self) -> None:
        with self._lock:
            self._load_unlocked()

    def _load_unlocked(self) -> None:
        loaded = {}
        self._exists = os.path.exists(self.path)
        if self._exists:
            with open(self.path, encoding="utf-8") as fp:
                loaded = yaml.safe_load(fp) or {}
            self._mtime = os.path.getmtime(self.path)
        else:
            self._mtime = None
        self._config = _deep_fill(schema.default_config(), loaded)
        self._errors = schema.validate(self._config)

    def maybe_reload(self) -> bool:
        """文件 mtime 变了就重载。渲染循环每轮调一次即可实现热重载。返回是否重载。"""
        with self._lock:
            try:
                cur = os.path.getmtime(self.path) if os.path.exists(self.path) else None
            except OSError:
                cur = None
            if cur != self._mtime:
                self._load_unlocked()
                return True
            return False

    # ---- 取 ----
    def get(self) -> dict:
        with self._lock:
            return self._config

    def errors(self) -> list:
        with self._lock:
            return list(self._errors)

    def status(self) -> dict:
        with self._lock:
            return {
                "config_exists": self._exists,
                "errors": list(self._errors),
                "enabled": schema.enabled_modules(self._config),
                "active_pages": schema.active_pages(self._config),
            }

    def redacted(self) -> dict:
        """给前端的脱敏配置:secret 字段已填→掩码,空→空。"""
        with self._lock:
            cfg = self._config
            out = {}
            for sec in schema.SCHEMA:
                d = dict(cfg.get(sec.key, {}))
                for f in sec.fields:
                    if f.secret:
                        d[f.key] = SECRET_MASK if (d.get(f.key) or "").strip() else ""
                    if f.type == "module_list":
                        d[f.key] = [self._redact_item(f, it) for it in d.get(f.key, [])]
                out[sec.key] = d
            return out

    @staticmethod
    def _redact_item(f, item):
        out = dict(item)
        for sub in (f.item_fields or []):
            if sub.secret:
                out[sub.key] = SECRET_MASK if (item.get(sub.key) or "").strip() else ""
        return out

    # ---- 写(设置网页保存)----
    def save(self, incoming: dict) -> list:
        """合并 incoming(可能只含部分模块)进当前配置,校验通过才原子写盘并重载。
        返回校验错误列表(非空=未保存)。"""
        with self._lock:
            merged = self._merge_for_save(self._config, incoming or {})
            errors = schema.validate(merged)
            if errors:
                return errors
            self._atomic_write(merged)
            self._load_unlocked()
            return []

    def _merge_for_save(self, current: dict, incoming: dict) -> dict:
        """以 current 为底合并 incoming。secret 字段提交掩码/空=保留原值。"""
        merged = _deep_fill(schema.default_config(), current)
        for sec in schema.SCHEMA:
            inc = incoming.get(sec.key)
            if inc is None:
                continue
            for f in sec.fields:
                if f.key not in inc:
                    continue
                val = inc[f.key]
                if f.type == "module_list":
                    merged[sec.key][f.key] = self._merge_list(f, merged[sec.key].get(f.key, []), val)
                elif f.secret and (not str(val).strip() or val == SECRET_MASK):
                    pass  # 保留原值
                else:
                    merged[sec.key][f.key] = val
        return merged

    @staticmethod
    def _merge_list(f, old_items, new_items):
        """列表整体替换;每项的 secret 子字段若提交掩码/空,按位置回填旧值。"""
        out = []
        for i, item in enumerate(new_items or []):
            filled = {}
            old = old_items[i] if i < len(old_items) else {}
            for sub in (f.item_fields or []):
                v = item.get(sub.key, "" if sub.secret else sub.default)
                if sub.secret and (not str(v).strip() or v == SECRET_MASK):
                    v = old.get(sub.key, "")
                filled[sub.key] = v
            out.append(filled)
        return out

    def _atomic_write(self, cfg: dict) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            yaml.safe_dump(cfg, fp, allow_unicode=True, sort_keys=False, default_flow_style=False)
        os.replace(tmp, self.path)


def load_config(path: str) -> ConfigManager:
    return ConfigManager(path)
