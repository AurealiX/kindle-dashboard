"""数据契约(Data Contract)—— 风格系统的地基。

风格(模板皮肤)引用的就是这里定义的字段。契约一旦冻结,所有风格共享同一套字段;
改契约会牵动所有风格,所以非必要不动。

本文件是契约的**权威定义**(docs/data-contract.md 是它的人类可读摘要,二者须同步)。

两个职责:
1. 描述每页 render context 有哪些字段(见 PAGES 与下方各 empty_* 函数的结构)。
2. 提供"降级空上下文" empty_context():缺数据 / 预览 / 数据源未配置时,
   渲染仍能出图而非报错(对应铁律「诚实降级」)。

注意:字段命名与结构 1:1 沿用现状(老 data_prep.py 的输出),保证已有 style_a 模板
零摩擦搬运。打印机字段当前贴合「单台 3D 打印机」,P2 抽象成通用 HA 实体卡片时再扩展契约。
"""

# 页面 key → 该页消费的契约段。
# 顶层时间/电池字段(now/time_hm/clock/battery)所有页可用。
# enabled 由配置决定(配置即页面);契约只负责"有这个页时,它能用哪些字段"。
PAGES = {
    "home":    {"title": "首页",   "section": "home",    "needs": ["weather", "reminders"]},
    "ai":      {"title": "AI 用量", "section": "ai",      "needs": ["ai_usage"]},
    "device":  {"title": "设备",   "section": "device",  "needs": ["devices"]},
    "ha":      {"title": "智能家居", "section": "ha",      "needs": ["ha_page"]},
    "printer": {"title": "打印机", "section": "printer", "needs": ["printer"]},
}

# 降级占位符:数字类用 0,文本类用 "--",列表类用 []。
DASH = "--"


def empty_top():
    """顶层字段(所有页共享)。"""
    return {
        "now": DASH,        # "05/27 14:30"  当前日期+时间
        "time_hm": DASH,    # "14:30"
        "clock": DASH,      # "14:30:05"
        "battery": {
            "level": DASH,      # int 0-100 或 "--"
            "charging": False,  # bool
            "has": False,       # bool,有无电池数据(无则模板不渲染电池块)
        },
    }


def empty_home():
    """首页:日期/农历/天气/日历/提醒。"""
    return {
        "date_md": DASH,    # "05/27"
        "date_dot": DASH,   # "05.27"
        "weekday": DASH,    # "周三"
        "lunar": DASH,      # "四月初一"
        "ganzhi": DASH,     # "丙午马年"
        "term": "",         # "今日芒种" / "夏至还有3天" / ""
        "year": 0, "month": 0,
        "weather": {        # 数据源 weather;未配置则全 "--"
            "city": "",              # 城市名(GeoAPI 反查 location);未配置/查不到则空,模板不显城市
            "temp": DASH, "cond": DASH, "feels": DASH, "humidity": DASH,
            "wind": DASH,            # "西北风3级"
            "today_range": DASH,     # "18–26°"
            "tmr_range": DASH,       # "19–27°"
            "tmr_cond": "",          # 明日天气文字
        },
        # 月历:周行数组,每格为 None(空)或 {d,l,today,holiday,weekend}
        "calendar": [],
        "reminders": {      # 数据源 reminders(Mac 推送);未配置则各列表为空
            "overdue": [],   # [{title, dt}]  dt 如 "05.20"
            "today": [],     # [{title, dt}]
            "upcoming": [],  # [{title, dt}]  dt 如 "明天"/"+3天"/"05.30"
            "total": 0,
        },
    }


def empty_ai():
    """AI 用量页:额度百分比 + 花费 + 7 天柱状图。"""
    return {
        "five_pct": 0, "five_reset": DASH,       # Claude 5h 额度已用% / 重置倒计时
        "week_pct": 0, "week_reset": DASH,       # Claude 周额度
        "cx_five_pct": 0, "cx_five_reset": DASH, # Codex 5h 额度
        "cx_week_pct": 0, "cx_week_reset": DASH, # Codex 周额度
        "today_cost": "$0",                      # 今日总花费
        "cc_cost": "$0", "cc_tok": "0",          # Claude 今日花费/token
        "cx_cost": "$0", "cx_tok": "0",          # Codex 今日花费/token
        "tok_7d": "0", "tok_30d": "0", "tok_all": "0",
        "chart": [],        # [{day:"27", cc_h:0-100, cx_h:0-100, val:"1.2M"}] 近 7 天
        "custom_total": "",  # 自定义倍率折算的今日实际花费,如 "¥12.34"
        "custom_name": "",   # 中转站/供应商名
    }


def empty_device_one():
    """单台设备指标。name=显示名(可自定义);show=各指标条是否显示(按用户勾选)。"""
    return {
        "name": "--",        # 显示名(local/ssh 来自配置;push 默认 hostname,可改)
        "cpu": 0,            # CPU 使用率 %
        "mem": 0,            # 内存使用率 %
        "mem_used": "0", "mem_total": "0",
        "net_rx": "0", "net_tx": "0",         # 网络收发速率
        "disk_r": "0", "disk_w": "0",         # 磁盘读写速率
        "vols": [],          # [{name, pct, used, total}] 各分区(按勾选过滤)
        # 字段勾选结果:留空配置=全 True;否则按用户勾选
        "show": {"cpu": True, "mem": True, "net": True, "disk_io": True},
    }


def empty_device():
    """设备监控页:动态机器列表(Windows/Linux/Mac 任意台)。
    machines = [empty_device_one(), ...];无机器时为空,该页隐藏。"""
    return {"machines": []}


def empty_ha():
    """智能家居实体墙;未配置/拉不到则卡片列表为空,该页隐藏。
    单张卡片对象(契约,冻结字段名):
        name        str   显示名(用户覆盖 or HA 友好名)
        kind        str   toggle/lock/cover/binary/sensor/climate/media/presence/text
        icon        str   MDI 图标名(mdi:xxx);空串=不显图标
        on          bool  激活态强调(开/有人/已锁/播放中…);sensor 恒 false
        state_text  str   主显文本(toggle/lock/cover/binary/climate/media/presence/text)
        value       str   主显数值(sensor;非 sensor 为空)
        unit        str   数值单位(sensor;如 °C / % / W)
        sub         str   次要行(climate 目标温度、media 标题…),可空
    模板主显:value 非空 → value 大字 + unit 小字;否则 state_text 大字。sub 非空加一行。
    """
    return {"cards": []}


def empty_printer():
    """3D 打印机页(依赖 Home Assistant)。printer 为 None 时整页降级/隐藏。"""
    return {
        "online": False,
        "printing": False,
        "state_text": DASH,      # "打印中"/"空闲"/"离线"...
        "progress": 0,           # 0-100
        "task": DASH,            # 文件名
        "layer": "0", "total_layer": "0",
        "remaining_text": DASH,  # "2小时15分"
        "eta_clock": DASH,       # 预计完成时刻 "16:45"
        "nozzle": DASH, "nozzle_t": DASH,   # 喷嘴温度 / 目标
        "bed": DASH, "bed_t": DASH,         # 热床温度 / 目标
        "speed": DASH,           # 速度档位
        "weight": DASH,          # 耗材重量
        "material": DASH,        # 耗材
        "cooling_fan": "0",      # 风扇转速
        "name": DASH,            # 打印机名
    }


def empty_context():
    """完整的降级上下文:所有页字段齐备、全为占位值。
    预览无数据、数据源未配置、采集失败时用它兜底,保证渲染出图不报错。"""
    ctx = empty_top()
    ctx["home"] = empty_home()
    ctx["ai"] = empty_ai()
    ctx["device"] = empty_device()
    ctx["ha"] = empty_ha()
    ctx["printer"] = None   # 默认无打印机
    return ctx
