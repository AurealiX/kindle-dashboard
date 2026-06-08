"""Tests for ccusage multi-device merge logic."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.sources.ccusage_merge import merge_all_devices, _merge_daily_multi, _merge_model_breakdowns


def test_merge_single_device():
    by_device = {
        "mac1": {
            "cc": {"daily": [
                {"date": "2026-06-07", "totalTokens": 1000, "totalCost": 5.0},
                {"date": "2026-06-06", "totalTokens": 500, "totalCost": 2.5},
            ]},
            "codex": {"daily": [
                {"date": "2026-06-07", "totalTokens": 2000, "totalCost": 10.0},
            ]},
        }
    }
    result = merge_all_devices(by_device)
    assert result["ok"] is True
    assert len(result["cc"]["daily"]) == 2
    assert result["cc"]["daily"][1]["totalTokens"] == 1000  # sorted by date, 06-07 is second
    assert result["codex"]["daily"][0]["totalTokens"] == 2000


def test_merge_two_devices_same_day():
    """核心需求:两台机器同一天的数据相加,不是覆盖也不是取 max。"""
    by_device = {
        "mac1": {
            "cc": {"daily": [
                {"date": "2026-06-07", "totalTokens": 1000, "totalCost": 5.0},
            ]},
            "codex": {"daily": [
                {"date": "2026-06-07", "totalTokens": 2000, "totalCost": 10.0},
            ]},
        },
        "mac2": {
            "cc": {"daily": [
                {"date": "2026-06-07", "totalTokens": 3000, "totalCost": 15.0},
            ]},
            "codex": {"daily": [
                {"date": "2026-06-07", "totalTokens": 4000, "totalCost": 20.0},
            ]},
        },
    }
    result = merge_all_devices(by_device)
    assert result["cc"]["daily"][0]["totalTokens"] == 4000   # 1000 + 3000
    assert result["cc"]["daily"][0]["totalCost"] == 20.0     # 5 + 15
    assert result["codex"]["daily"][0]["totalTokens"] == 6000  # 2000 + 4000
    assert result["codex"]["daily"][0]["totalCost"] == 30.0    # 10 + 20


def test_merge_two_devices_different_days():
    """不同天的数据各归各天。"""
    by_device = {
        "mac1": {
            "cc": {"daily": [
                {"date": "2026-06-07", "totalTokens": 1000, "totalCost": 5.0},
            ]},
            "codex": {"daily": []},
        },
        "mac2": {
            "cc": {"daily": [
                {"date": "2026-06-06", "totalTokens": 2000, "totalCost": 10.0},
            ]},
            "codex": {"daily": []},
        },
    }
    result = merge_all_devices(by_device)
    assert len(result["cc"]["daily"]) == 2
    day6 = next(d for d in result["cc"]["daily"] if d["date"] == "2026-06-06")
    day7 = next(d for d in result["cc"]["daily"] if d["date"] == "2026-06-07")
    assert day6["totalTokens"] == 2000
    assert day7["totalTokens"] == 1000


def test_merge_model_breakdowns_list_format():
    """Claude 的 modelBreakdowns 是列表格式。"""
    entries = [
        {"date": "2026-06-07", "totalTokens": 100, "totalCost": 1.0,
         "modelBreakdowns": [
             {"modelName": "opus", "totalTokens": 60, "totalCost": 0.6},
             {"modelName": "sonnet", "totalTokens": 40, "totalCost": 0.4},
         ]},
        {"date": "2026-06-07", "totalTokens": 200, "totalCost": 2.0,
         "modelBreakdowns": [
             {"modelName": "opus", "totalTokens": 150, "totalCost": 1.5},
             {"modelName": "haiku", "totalTokens": 50, "totalCost": 0.1},
         ]},
    ]
    models = _merge_model_breakdowns(entries)
    assert models["opus"]["tokens"] == 210   # 60 + 150
    assert models["opus"]["cost"] == 2.1     # 0.6 + 1.5
    assert models["sonnet"]["tokens"] == 40
    assert models["haiku"]["tokens"] == 50


def test_merge_model_breakdowns_dict_format():
    """Codex 的 models 可能是字典格式。"""
    entries = [
        {"date": "2026-06-07", "totalTokens": 100, "totalCost": 1.0,
         "models": {"gpt-5": {"totalTokens": 100, "costUSD": 1.0}}},
        {"date": "2026-06-07", "totalTokens": 200, "totalCost": 2.0,
         "models": {"gpt-5": {"totalTokens": 200, "costUSD": 2.0}}},
    ]
    models = _merge_model_breakdowns(entries)
    assert models["gpt-5"]["tokens"] == 300
    assert models["gpt-5"]["cost"] == 3.0


def test_merge_empty_devices():
    assert merge_all_devices({}) == {"ok": True, "cc": {"daily": []}, "codex": {"daily": []}}
    assert merge_all_devices(None) == {"ok": True, "cc": {"daily": []}, "codex": {"daily": []}}


def test_merge_bad_data_tolerant():
    """坏数据不崩,跳过。"""
    by_device = {
        "bad1": "not a dict",
        "bad2": {"cc": "not a dict"},
        "good": {"cc": {"daily": [{"date": "2026-06-07", "totalTokens": 100, "totalCost": 1.0}]}, "codex": {"daily": []}},
    }
    result = merge_all_devices(by_device)
    assert result["cc"]["daily"][0]["totalTokens"] == 100


def test_merge_codex_costUSD_field():
    """Codex 用 costUSD 而非 totalCost。"""
    by_device = {
        "m1": {"cc": {"daily": []}, "codex": {"daily": [
            {"date": "2026-06-07", "totalTokens": 500, "costUSD": 3.0},
        ]}},
        "m2": {"cc": {"daily": []}, "codex": {"daily": [
            {"date": "2026-06-07", "totalTokens": 800, "costUSD": 5.0},
        ]}},
    }
    result = merge_all_devices(by_device)
    assert result["codex"]["daily"][0]["totalTokens"] == 1300
    assert result["codex"]["daily"][0]["totalCost"] == 8.0


def test_merge_daily_multi_sorted():
    """结果按日期升序排列。"""
    dailies = [
        [{"date": "2026-06-09", "totalTokens": 1, "totalCost": 0}],
        [{"date": "2026-06-07", "totalTokens": 2, "totalCost": 0}],
        [{"date": "2026-06-08", "totalTokens": 3, "totalCost": 0}],
    ]
    result = _merge_daily_multi(dailies)
    dates = [d["date"] for d in result]
    assert dates == ["2026-06-07", "2026-06-08", "2026-06-09"]


if __name__ == "__main__":
    test_merge_single_device()
    test_merge_two_devices_same_day()
    test_merge_two_devices_different_days()
    test_merge_model_breakdowns_list_format()
    test_merge_model_breakdowns_dict_format()
    test_merge_empty_devices()
    test_merge_bad_data_tolerant()
    test_merge_codex_costUSD_field()
    test_merge_daily_multi_sorted()
    print("All ccusage merge tests passed!")
