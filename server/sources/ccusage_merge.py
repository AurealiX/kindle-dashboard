"""多设备 ccusage 合并:按日期+模型相加(非覆盖、非取 max)。

多台机器各推各的 ccusage 数据到看板服务,服务需要把它们合并成统一视图——
同一天同一模型的 token/花费直接相加。这与老 ccusage-web 的"多源相加"语义一致。

公共函数 merge_all_devices(by_device) 是唯一入口:
输入 = {device_id: {"cc": {"daily": [...]}, "codex": {"daily": [...]}}, ...}
输出 = {"ok": True, "cc": {"daily": merged}, "codex": {"daily": merged}}
"""


def _merge_model_breakdowns(entries):
    """合并多条 daily 记录里的 modelBreakdowns(Claude) 或 models(Codex)。
    同模型的 tokens/cost 相加。"""
    merged = {}
    for entry in entries:
        breakdowns = entry.get("modelBreakdowns") or entry.get("models") or {}
        if isinstance(breakdowns, list):
            for item in breakdowns:
                name = item.get("modelName") or item.get("model") or "unknown"
                merged.setdefault(name, {"tokens": 0, "cost": 0})
                merged[name]["tokens"] += item.get("totalTokens", 0) or item.get("tokens", 0)
                merged[name]["cost"] += item.get("totalCost", 0) or item.get("costUSD", 0) or item.get("cost", 0)
        elif isinstance(breakdowns, dict):
            for name, vals in breakdowns.items():
                if not isinstance(vals, dict):
                    continue
                merged.setdefault(name, {"tokens": 0, "cost": 0})
                merged[name]["tokens"] += vals.get("totalTokens", 0) or vals.get("tokens", 0)
                merged[name]["cost"] += vals.get("totalCost", 0) or vals.get("costUSD", 0) or vals.get("cost", 0)
    return merged


def _merge_daily_multi(all_dailies):
    """将多个 daily 数组按日期合并。同日 totalTokens/totalCost 相加,modelBreakdowns/models 合并。"""
    by_date = {}
    for daily in all_dailies:
        if not isinstance(daily, list):
            continue
        for item in daily:
            if not isinstance(item, dict):
                continue
            d = item.get("date")
            if not d:
                continue
            by_date.setdefault(d, []).append(item)

    result = []
    for d in sorted(by_date.keys()):
        entries = by_date[d]
        total_tokens = sum(e.get("totalTokens", 0) for e in entries)
        total_cost = sum(e.get("totalCost", 0) or e.get("costUSD", 0) for e in entries)
        merged_entry = {"date": d, "totalTokens": total_tokens, "totalCost": total_cost}
        models = _merge_model_breakdowns(entries)
        if models:
            merged_entry["modelBreakdowns"] = models
        result.append(merged_entry)
    return result


def merge_all_devices(by_device):
    """合并所有设备的 ccusage 数据。

    Args:
        by_device: {device_id: {"cc": {"daily": [...]}, "codex": {"daily": [...]}}}

    Returns:
        {"ok": True, "cc": {"daily": merged_cc}, "codex": {"daily": merged_codex}}
    """
    all_cc = []
    all_codex = []
    for _dev_id, data in (by_device or {}).items():
        if not isinstance(data, dict):
            continue
        cc = data.get("cc")
        if isinstance(cc, dict):
            cc_daily = cc.get("daily")
            if isinstance(cc_daily, list):
                all_cc.append(cc_daily)
        cx = data.get("codex")
        if isinstance(cx, dict):
            cx_daily = cx.get("daily")
            if isinstance(cx_daily, list):
                all_codex.append(cx_daily)

    return {
        "ok": True,
        "cc": {"daily": _merge_daily_multi(all_cc)},
        "codex": {"daily": _merge_daily_multi(all_codex)},
    }
