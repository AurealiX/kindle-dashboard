# Home Assistant 通用实体页 —— 施工图

> **本文档自包含,交给开发 AI 即可实现。** 实现前先读项目根 `CLAUDE.md`(三条铁律)、`docs/data-contract.md`(契约约定)、`server/sources/homeassistant.py`(现有 HA 集成)、`web/setup.html`(设置页表单 + 城市选择器 `cityField` 是本页"实体选择器"的范本)。
>
> 状态:**已实现并真机验证(2026-06-07)**。本文档保留为设计/契约依据。落地范围:数据/采集/配置/`/api/ha-entities`/设置页/`styles/style_a/ha.html` 全部完成,连真实 HA 出图通过;两处决策落地为「内嵌 SVG 精选图标集(非 @mdi 字体)」+「先只做 style_a」。其余 6 套风格的 ha 页见 **`docs/ha-page-styles-spec.md`**(独立施工图)。实现进度见 `CLAUDE_TASK_QUEUE.md`。

## 0. 一句话目标

填好 HA 地址+令牌后,用户在设置网页**搜索并挑选自己关心的 HA 实体**(灯、温湿度、门窗、空调、门锁……),看板上多出一个 **`ha` 页**,把这些实体渲染成一面 **HomeKit 风格的自适应瓦片墙**,只读显示实时状态。全程不碰代码、不填实体 ID。

## 1. 范围与非目标

**做:**
- 只读展示用户挑选的任意 HA 实体的实时状态。
- 自适应瓦片:开关类显示"开/关"+图标,传感器类显示"数值+单位",门锁/门窗/空调/媒体等各有映射(见 §5)。
- 设置网页里的"实体选择器":搜实体名→候选→加成卡片→可改显示名/图标/排序/删除。

**不做(明确非目标):**
- ❌ **不做控制/执行**(开灯关锁等)。Kindle 是只读看板,本页纯展示。绝不调用 HA 的 service / 不发 POST 改状态。
- ❌ **不做分组**(本期决策:一组平铺。分组/按区域是未来扩展,见 §11)。
- ❌ **不替换打印机页**。打印机页(`printer`)继续独立存在;本页是它的通用化方向(`CLAUDE.md` 已注明 P2 收敛),但**本期两页并存,互不影响**。

## 2. 与现有代码的关系

| 现有 | 本页复用/参照 |
|---|---|
| `home_assistant` 配置段(url+token) | **直接复用**,不改。本页和打印机页共享这一对凭据。 |
| `server/sources/homeassistant.py` | 扩展:同一次 `/api/states` 拉取,**既建 printer 也建 ha 卡片**(别拉两次)。 |
| `/api/city-search` + `web/setup.html` 的 `cityField` | **结构范本**:实体选择器 = 城市选择器的同构实现(后端代理 HA、前端搜索候选选中)。 |
| `devices` 的 `module_list` + `machineCard` | **结构范本**:实体卡片列表 = 设备机器卡片列表的同构实现(可增删、每项一个选择器)。 |
| 渲染管线 `_merge`(None=不覆盖) | **复用降级语义**:HA 拉取失败返回 None → 不覆盖 `cache["ha"]` → 保留上一帧。 |

## 3. 数据流(与现状一致)

```
config.ha_page.entities (用户挑的实体列表)
        │
        ▼
homeassistant.collect(cfg)  ── 一次 GET /api/states ──►  HA
        │  按 entities 逐个匹配 + 按 §5 映射成卡片
        ▼
cache["ha"] = {"cards": [ {name,kind,icon,on,state_text,value,unit,sub}, ... ]}
        │
        ▼
build_context → ctx["ha"]  (缺/降级走 contract.empty_ha())
        │
        ▼
styles/<style>/ha.html  ── 自适应瓦片渲染 ──►  PNG
```

## 4. 配置模型(schema 改动)

### 4.1 新增 Section(加到 `server/config/schema.py` 的 SCHEMA,放在 `printer` 段之后)

```python
Section(
    key="ha_page", label="智能家居", page="ha",
    help="把 Home Assistant 里你关心的实体显示成一面卡片墙(需先配好上面的 Home Assistant 地址+令牌)。",
    enable_when=["entities"],   # 选了至少一个实体才启用;list 的特判见 4.2
    fields=[
        Field("entities", "实体卡片", "module_list", default=[],
              item_fields=[
                  Field("entity_id", "实体", "ha_entity", "", required=True,
                        help="从 HA 搜索选择,自动带出名称和图标。"),
                  Field("name", "显示名", "str", "",
                        help="留空=用 HA 的友好名(friendly_name)。"),
                  Field("icon", "图标", "str", "", hidden=True,
                        help="mdi:xxx;留空=用 HA 实体自带图标。由实体选择器写入,高级可手填。"),
              ]),
    ],
),
```

> 新增字段类型 `ha_entity`:在 `_check_type` 里按 `str` 处理(`if t in ("str","enum","city","ha_entity")`),设置页 `renderField` 给它专门的实体选择器控件(§7)。

### 4.2 `enabled_modules` 特判(`schema.py`)

`ha_page` 和 `devices` 一样,启用条件是"列表非空",不是"某字段填了"。在 `enabled_modules` 里加:

```python
if sec.key in ("devices",):                 # 现有
    out[sec.key] = len(secd.get("machines", []) or []) > 0
    continue
if sec.key == "ha_page":                     # 新增
    out[sec.key] = len(secd.get("entities", []) or []) > 0
    continue
```

### 4.3 `active_pages` 映射(`schema.py`)

`page_ready` 字典加一行:

```python
"ha": enabled.get("ha_page"),
```

`default_order` 里把 `"ha"` 插进去(建议放 `printer` 前或后,顺序即轮播顺序):
```python
default_order = ["home", "ai", "device", "ha", "printer"]
```

### 4.4 `config.example.yaml` 增段

```yaml
# 智能家居实体墙(经 Home Assistant)——选了实体才出这一页
ha_page:
  entities: []
  # 用设置网页搜实体添加更方便。手填示例:
  #   - entity_id: light.living_room
  #     name: 客厅灯        # 留空用 HA 友好名
  #     icon: ""            # 留空用 HA 自带图标
```

## 5. 实体类型 → 卡片内容映射(核心)

采集器对每个配置的 `entity_id`,在 `/api/states` 结果里找到该实体,读 `state` + `attributes`,按下表产出一张卡片。**判定顺序:先按 domain,再用 device_class 细分。**

| HA domain | device_class 细分 | `kind` | 主显 | `on` 语义 | 备注 |
|---|---|---|---|---|---|
| `light` `switch` `fan` `input_boolean` `automation` `script` `siren` `humidifier` | — | `toggle` | state_text=`开`/`关` | state=="on" | 图标在 on 时"实心强调" |
| `lock` | — | `lock` | `已锁`/`未锁` | state=="locked" | |
| `cover` | — | `cover` | `开`/`关`/`N%` | state=="open" | 有 `current_position` 则显 `N%` |
| `binary_sensor` | `door`/`window`/`garage_door` | `binary` | `开`/`关` | state=="on" | |
| `binary_sensor` | `motion`/`occupancy`/`presence` | `binary` | `有人`/`无人` | state=="on" | |
| `binary_sensor` | `moisture` | `binary` | `漏水`/`正常` | state=="on" | on=异常 |
| `binary_sensor` | `problem`/`smoke`/`gas` | `binary` | `异常`/`正常` | state=="on" | on=异常 |
| `binary_sensor` | 其它/无 | `binary` | `是`/`否` | state=="on" | |
| `sensor` | 任意(temperature/humidity/power/energy/illuminance/co2/pm25/battery/pressure…) | `sensor` | value=`state`,unit=`attributes.unit_of_measurement` | 恒 false | 数值大字 + 单位小字 |
| `climate` | — | `climate` | state_text=hvac 模式中文(`制冷`/`制热`/`自动`/`关`),value=`current_temperature` | state!="off" | sub=`目标 {temperature}°` |
| `media_player` | — | `media` | `播放中`/`暂停`/`空闲` | state=="playing" | sub=`media_title`(截断) |
| `person` `device_tracker` | — | `presence` | `在家`/`外出` | state=="home" | |
| `weather` | — | `sensor` | value=`temperature`,unit=`°` | false | 一般首页已有天气,可不放 |
| 其它任意 domain | — | `text` | state_text=`state` 原文 | false | 兜底:总有显示,不报错 |

**hvac 模式中文映射**(climate 的 state):`heat→制热, cool→制冷, heat_cool→自动, auto→自动, dry→除湿, fan_only→送风, off→关`。

**降级规则(诚实降级铁律):**
- 实体在 `/api/states` 里**找不到**(被删/写错):`{kind:"text", name: 显示名 or entity_id, state_text:"未知实体", on:false}`。
- `state` 是 `unavailable`/`unknown`/空:value/state_text 显 `--`,`on:false`,sensor 的 unit 仍保留。
- 整个 HA 拉不通:采集器返回 None(见 §6),**不覆盖** `cache["ha"]`,保留上一帧。

## 6. 后端实现

### 6.1 扩展 `server/sources/homeassistant.py`

重构成"拉一次 states,建两类数据":

```python
def collect(cfg):
    ha = (cfg or {}).get("home_assistant", {})
    url = (ha.get("url") or "").strip().rstrip("/")
    token = (ha.get("token") or "").strip()
    if not (url and token):
        return None
    # 只要配了 HA 就拉一次 states(打印机页 or 实体页任一需要)
    pr_cfg = (cfg or {}).get("printer", {})
    entities = (cfg.get("ha_page", {}) or {}).get("entities", []) or []
    if not ((pr_cfg.get("enabled") and pr_cfg.get("entity_prefix")) or entities):
        return None
    try:
        states = httpx.get(f"{url}/api/states",
                           headers={"Authorization": f"Bearer {token}"},
                           timeout=8).json()
    except Exception as e:
        print(f"[homeassistant] {e}")
        return None     # 不覆盖 cache,保留上一帧
    out = {}
    if pr_cfg.get("enabled") and pr_cfg.get("entity_prefix"):
        out["printer"] = _build_printer(states, pr_cfg.get("entity_prefix"))  # 现有逻辑搬进来
    if entities:
        out["ha"] = {"cards": [_build_card(states, e) for e in entities]}
    return out or None
```

`_build_card(states, ent)`:按 §5 映射。`states` 建议先转成 `{entity_id: state_obj}` 字典加速查找。

> ⚠️ 现有 `collect` 的打印机判定含 `pr_cfg.get("enabled")`;重构后保持打印机行为**完全不变**(回归测试 `test_*` 必须全绿)。

### 6.2 新增实体选择器接口(`server/app.py`)

照搬 `/api/city-search` 的结构(凭据只在服务端用,不回传):

```python
@app.get("/api/ha-entities")
def api_ha_entities(q: str = "", domain: str = ""):
    ha = cm.get().get("home_assistant", {})
    url = (ha.get("url") or "").strip().rstrip("/")
    token = (ha.get("token") or "").strip()
    if not (url and token):
        return JSONResponse({"ok": False,
            "error": "请先填写并【保存】Home Assistant 的地址和令牌,再选实体。"}, status_code=400)
    try:
        items = homeassistant.list_entities(url, token, q, domain)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"读取实体失败:{e}"}, status_code=502)
    return {"ok": True, "entities": items}
```

`homeassistant.list_entities(url, token, q, domain)`:GET `/api/states`,每个实体映射为
`{entity_id, name(friendly_name or entity_id), domain(entity_id 前缀), device_class, state, unit, icon(attributes.icon or "")}`;
按 `q`(匹配 entity_id 或 name,不区分大小写)和 `domain` 过滤;按 name 排序;**截断到前 ~50 条并在返回里标 `truncated:true`**(不静默截断,前端提示"结果较多,请细化关键词")。

## 7. 设置网页 UI

两块,都在 `web/setup.html`:

### 7.1 `ha_page.entities` 卡片列表(参照 `renderDevices`/`machineCard`)

- module_list 目前只有 `devices` 特判;给 `ha_page` 加一个同构的 `renderHaEntities(sec)`:遍历 `entities` 渲染卡片,底部"+ 添加实体"。
- 每张卡片:**实体选择器**(见 7.2)+ 显示名输入(占位"留空用 HA 名")+ 折叠"高级:手填图标 mdi:xxx" + 删除按钮 + 上下移排序。
- `collect()` 里加 `ha_page` 的收集分支(照 `devices` 写):产出 `{entities:[{entity_id,name,icon}, ...]}`。

### 7.2 实体选择器控件(`ha_entity` 类型,参照 `cityField`)

- 搜索框 + domain 下拉过滤(灯/开关/传感器/…可选,或留空全部)+ 搜索按钮。
- 候选列表每项显示:**友好名** + 灰字 `entity_id · domain · 当前状态`(消歧,像城市选择器带省/市)。
- 选中 → 写入该卡片的 `entity_id`(隐藏值)、回填显示名占位、若卡片 icon 为空则带出 HA 的 `icon`。
- HA 未配/未保存 → 搜索时显示后端返回的 400 提示文案。

## 8. 数据契约扩展

### 8.1 `server/render/contract.py`

`PAGES` 加:`"ha": {"title": "智能家居", "section": "ha", "needs": ["ha_page"]}`(needs 用于文档/校验,按现有风格填)。

新增 `empty_ha()`:
```python
def empty_ha():
    """智能家居实体墙;未配置/拉不到则卡片列表为空,该页隐藏。"""
    return {"cards": []}   # 每张卡片结构见下
```
`build_context` 里 `ctx["ha"] = cache.get("ha") or empty_ha()`。

**单张卡片对象(契约,冻结字段名):**
```
{
  "name": "客厅灯",          # str  显示名(用户覆盖 or HA 友好名)
  "kind": "toggle",          # str  toggle/lock/cover/binary/sensor/climate/media/presence/text
  "icon": "mdi:lightbulb",   # str  MDI 图标名;空串=不显图标
  "on":   true,              # bool 激活态强调(开/有人/已锁/播放中…);sensor 恒 false
  "state_text": "开",        # str  主显文本(toggle/lock/cover/binary/climate/media/presence/text)
  "value": "",               # str  主显数值(sensor;非 sensor 为空)
  "unit":  "",               # str  数值单位(sensor;如 °C / % / W)
  "sub":   ""                # str  次要行(climate 目标温度、media 标题…),可空
}
```
模板渲染主显的逻辑:`value` 非空 → 显 `value` 大字 + `unit` 小字;否则显 `state_text` 大字。`sub` 非空则加一行小字。

### 8.2 `docs/data-contract.md`

加 `ha` 页一节,把上面卡片字段表搬进去,并在"页面→数据段"表加一行 `ha | 智能家居 | ha | Home Assistant + 选了实体`。

## 9. 渲染设计(参考瓦片布局,先做 `styles/style_a/ha.html`)

**画布 800×600 横屏**(与其它页一致,PIL 再旋转)。

### 9.1 网格

- 自适应列数:按卡片数取 `cols = ceil(sqrt(n))` 上限 4(800 宽下 4 列舒适);`grid-template-columns: repeat(cols, 1fr)`,`gap` 10px。
- 容量:4×3=12 张瓦片在 800×600 下清晰。**建议用户挑 ≤12 个**;`>12` 时不静默丢——实现二选一:(a)瓦片整体缩小自适应到 5 列;(b)超出分到第二张 `ha` 页轮播。本期取 (a) 并在 §6 采集时 `log` 实际渲染张数。

### 9.2 单张瓦片解剖

```
┌─────────────┐
│  [图标 28px] │   ← MDI 字体,on 时实心/加粗,off 时描边/淡灰
│  名称(12px) │   ← 单行省略
│  主显(大)   │   ← value+unit(20/11px) 或 state_text(20px,加粗)
│  sub(10px)  │   ← 可空
└─────────────┘
```
- 边框 1px 浅灰圆角;**on 态**:左上角加一个实心小圆点 或 整框描边加重(墨水屏靠"实心 vs 描边"区分,别靠颜色)。
- 渲染纪律(CLAUDE.md):铺满不留大块白;大色块用斜线填充代替实心黑;`{{ "%02d"|format(x) }}` 补零。

### 9.3 图标方案(MDI 字体)

- HA 每个实体自带 `attributes.icon`(如 `mdi:lightbulb`),采集器直接透传到 `card.icon`;无则按 domain 给默认(`light→mdi:lightbulb, switch→mdi:power-socket, sensor+temperature→mdi:thermometer, lock→mdi:lock, ...`,给一张 ~20 行的 domain→mdi 默认表)。
- 前端/模板:`card.icon` = `"mdi:lightbulb"` → CSS class `mdi mdi-lightbulb`(@mdi/font 的用法)。
- **打包 @mdi/font**(woff2 + css,约 1.2MB)进 `styles/`(或 `server/render/assets/`),`style.css` 里 `@font-face` 引本地文件。本地 Chromium 读本地文件,零网络、即时。
  - 备选(更轻):只内嵌 ~20 个常用 domain 的 inline SVG,放弃 HA 的逐实体 icon。覆盖少、要维护映射,**不推荐**,除非介意 1.2MB。

### 9.4 降级渲染

- `cards` 为空:该页本就不在 active_pages(配置即页面),不会渲染。
- 个别卡片降级(`--`/`未知实体`):正常渲染该瓦片,主显 `--`,不影响其它瓦片。

## 10. 验收标准 & 测试

**验收(非科班用户照 README 能走通):**
1. 填好 HA 地址+令牌并保存 → 设置页"智能家居"段能搜到实体。
2. 搜"客厅"→ 候选列出匹配实体(带 entity_id/状态)→ 点选加成卡片。
3. 加几个不同类型(灯/温度/门锁)→ 保存 → 右侧实时预览出现 `ha` 页瓦片墙,状态正确。
4. 把某实体在 HA 里关掉/改值 → 下一轮(≤30s)看板瓦片跟着变。
5. 删掉一个 HA 实体 → 对应瓦片显"未知实体",其它不受影响,不报错。

**自动化测试(`tests/`,用 states fixture,不打网络):**
- `_build_card` 映射:给一份含 light/sensor/lock/climate/binary_sensor/未知 的 `states` fixture,断言每张卡片的 `kind/on/state_text/value/unit`。
- 降级:`unavailable` state → `--`;缺失 entity → `未知实体`。
- `/api/ha-entities` 未配 HA → 400 + 提示(用空配置 TestClient)。
- `active_pages`:配了 entities → 含 `ha`;空 → 不含。
- 渲染冒烟:`styles/style_a/ha.html` 用 sample cards 渲染出图不报错(并入现有 `test_render_smoke`)。
- 打印机回归:重构 `homeassistant.collect` 后,原打印机相关测试全绿。

## 11. 未来扩展(本期不做,留好接口)

- **分组/按区域**:本期一组平铺。未来可加 `card.group` 字段 + 按 HA Area 自动分组(Area 映射需 `POST /api/template` 渲染 `area_name(entity_id)`,REST 可拿,无需 websocket)。契约里 `card` 预留 `group` 不会破坏现状。
- **打印机页收敛**:把打印机做成 ha 卡片的一个预设组,最终下线专用 `printer` 页(CLAUDE.md P2 目标)。
- **阈值高亮**:sensor 超阈值(如温度>30)时 `on:true` 强调。需在 schema 给每卡片可选 `warn_above/warn_below`。

## 12. HA API 速查(实现者参考)

- **令牌**:HA → 左下角用户头像 → 底部"长期访问令牌" → 创建令牌。填进设置页"Home Assistant · 长期访问令牌"。
- **认证**:所有请求头 `Authorization: Bearer <token>`。
- **`GET /api/states`**:返回全部实体数组,每项 `{entity_id, state, attributes, last_changed, ...}`。`attributes` 常见键:`friendly_name`、`unit_of_measurement`、`device_class`、`icon`(mdi:)、`current_temperature`、`temperature`、`current_position`、`media_title`、`hvac_action`。
- **`GET /api/states/<entity_id>`**:单个实体(本页用全量 states 即可,不必逐个)。
- **`POST /api/template`**(未来分组用):body `{"template": "{{ area_name('light.living_room') }}"}` 返回区域名。
- `state` 特殊值:`unavailable`(设备离线)、`unknown`(无数据)——都按降级处理。

---

**实现顺序建议**:① schema+契约(4/8)→ ② 采集器映射+单测(5/6.1/10)→ ③ 实体选择器接口+设置页(6.2/7)→ ④ style_a/ha.html 瓦片+MDI 字体(9)→ ⑤ 端到端验收(10)。①②可独立先行,不依赖前端。
