# HA「智能家居」页 —— 其余 6 套风格施工图

> **本文档自包含,交给开发 AI 即可实现。** 目标:给 `bento`/`blueprint`/`gauge`/`minimal`/`newspaper`/`terminal` 这 6 套风格各补一个 `ha.html`,让"智能家居实体墙"在每套皮肤下都有对应观感。
>
> 实现前先读:项目根 `CLAUDE.md`(三条铁律 + 渲染纪律)、`docs/data-contract.md` 的 **`ha` 段**(数据契约,已冻结)、**参考实现 `styles/style_a/ha.html`**(已上线、用户认可的基准版)、以及**你要做的那套风格自己的** `styles/<风格>/style.css` + `home.html`/`device.html`(学它的视觉语言)。
>
> 状态:✅ **已实现(2026-06-07)**。6 套 `ha.html` 已交付(bento/blueprint/gauge/minimal/newspaper/terminal),复用 style_a 内嵌 SVG 图标集、统一自适应网格/空态/灰度 on-off;冒烟测试参数化覆盖全风格全页(94 绿)。本文保留作设计依据。

## 0. 一句话目标

`ha` 页(智能家居实体墙)目前只有 `style_a` 一套模板。其余 6 套风格切到该页时,系统检测到缺 `ha.html` 会**自动跳过**(`server/app.py` 的 `styles.has_page` 判定,不报错)。本任务就是把这一页**铺到全部 6 套风格**,每套都用**它自己的视觉语言**渲染同一批数据。

## 1. 你要交付什么

6 个文件,每个是该风格目录下的一个新模板:
```
styles/bento/ha.html
styles/blueprint/ha.html
styles/gauge/ha.html
styles/minimal/ha.html
styles/newspaper/ha.html
styles/terminal/ha.html
```
**只新增这 6 个文件,不改任何 Python、不改 schema、不改数据契约、不改 style_a。** 数据层已经齐备,你只做"皮肤"。

## 2. 数据契约(只读,冻结 —— 别改、别假设多余字段)

模板拿到的上下文里,本页只消费 `ha.cards`(一个列表)。每张卡片字段(与 `style_a/ha.html`、`docs/data-contract.md` 一致):

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | str | 显示名(用户覆盖 or HA 友好名) |
| `kind` | str | `toggle`/`lock`/`cover`/`binary`/`sensor`/`climate`/`media`/`presence`/`text` |
| `icon` | str | MDI 图标名(`mdi:xxx`);空串=不显图标 |
| `on` | bool | 激活态(开/有人/已锁/播放中…);`sensor` 恒 `false` |
| `state_text` | str | 主显文本(非 sensor 类) |
| `value` | str | 主显数值(sensor;非 sensor 为空) |
| `unit` | str | 数值单位(sensor;如 `°C`/`%`/`W`) |
| `sub` | str | 次要行(climate 目标温度、media 标题…),可空 |

**主显规则(所有风格统一)**:`value` 非空 → 显 `value` 大字 + `unit` 小字;否则显 `state_text` 大字。`sub` 非空再加一行小字。

顶层还有 `now` / `time_hm` / `battery`(页眉页脚用,和其它页一样)。**不要**引用 `ha` 之外的业务段。

## 3. 通用规则(6 套都必须遵守)

1. **画布 800×600 横屏**,渲染后由管线统一 PIL 旋转+灰度(你不管旋转)。
2. **纯灰度,on/off 不靠颜色**(CLAUDE.md 铁律 + 墨水屏):激活态靠**实心 vs 描边、线宽、填充、字重**表达,用你这套风格已有的手法(见 §5)。
3. **铺满不留大块白**;大色块用**斜线/网点填充**代替整片实心黑(各风格 css 已有 `.hatch` 类或等价物,直接用)。
4. **样式注入**:模板头部 `{{ css|safe }}`(和其它页一致),复用该风格 `style.css` 的变量/工具类(`--ink/--ink2/--ink3`、`.masthead`、`.footer`、`.hatch` 等),**不要重新发明配色/间距**。
5. **页眉页脚**:沿用该风格其它页的 `.masthead`(报头)和 `.footer`(页脚)结构,标题写"家庭概览"或符合该风格的等价物;页脚右侧可放 `{{ on_n }} 开启 · {{ cards|length }} 实体` 这类汇总(`on_n` 自己用 `cards|selectattr('on')|list|length` 算)。
6. **自适应网格(列数,统一公式)**:
   ```jinja
   {%- set n = cards|length -%}
   {%- set ce = (n ** 0.5)|round(0, 'ceil')|int -%}
   {%- if n > 12 -%}{%- set cols = 5 -%}{%- elif ce > 4 -%}{%- set cols = 4 -%}{%- elif ce < 1 -%}{%- set cols = 1 -%}{%- else -%}{%- set cols = ce -%}{%- endif -%}
   ```
   即 `cols = ceil(sqrt(n))`,上限 4;`n>12` 时放到 5 列缩小。容量参考 4×3=12 在 800×600 清晰。
7. **降级**:`cards` 为空时该页本不会被渲染(配置即页面),但**仍要写一个空态分支**(`{% if cards %}…{% else %}…{% endif %}`),给个"在设置页添加 HA 实体"的提示,保证预览/冒烟不报错。单卡降级(`state_text` 为 `--` 或 `未知实体`)正常渲染,不特殊处理。
8. **Jinja 无 `zfill`**,补零用 `{{ "%02d"|format(x) }}`;数字加 `.tnum`(各风格已定义 tabular-nums)。

## 4. 图标(直接复用 style_a 的内嵌 SVG 集)

`style_a/ha.html` 顶部有一段 Jinja 定义的 `ICONS`(mdi 名 → inline SVG)+ `KIND_ICONS`(按 kind 兜底)+ `S`(svg 包裹前缀)。**整段复制到你的模板里复用**,查找链:
```jinja
{% set glyph = ICONS.get(c.icon) or KIND_ICONS.get(c.kind) or KIND_ICONS['text'] %}
... {{ (S + glyph + '</svg>')|safe }}
```
保证每张卡片都有图标。**不要打包字体文件**(@mdi/font 等),保持零网络、零二进制。图标用 `stroke="currentColor"`,颜色由你的 CSS 用 `color` 控制(激活态反白时把 `color` 设白即可,见 style_a 的 `.tile.on .disc .ic{color:#fff}`)。

> 若某风格的视觉语言更适合"无独立图标"(如 `minimal` 极简、`terminal` 用字符),可以弱化或省略图标——但**必须有清晰的 kind/状态表达**,别让用户分不清这是什么设备、开还是关。

## 5. 各风格的具体方向(对症下药)

> 共同点:同一批 `ha.cards`,做成一面"实体墙"。差异在于**单元的视觉语言**,照搬该风格已有页面(`home/device`)的手法。

- **bento(便当格子)**:每个实体一个**圆角柔灰卡片**,模块化便当排布,大号圆润数字。激活态用**填充更深的灰卡 + 实心图标**,关态用浅灰卡。层级靠填充深浅 + 字号(严格字号阶 11/13/16/20/26/40/64)。最贴近 style_a,但用"填充分层"而非"描边盘"。
- **blueprint(工程蓝图)**:每个实体一个**双线图框面板**,标注/量取式数值,带工程标注小字(如 `[ON]`/`[OFF]`、device_class 当英文标签)。激活态用**加重图框线 + 网点填充角标**。底纹方格 + 发丝线,等宽技术字体。
- **gauge(模拟仪表)**:**圆形语言**是这套的灵魂。sensor 类做成**半圆/环形小表盘 + 指针**(value 当读数,可按合理量程画弧);开关类做成**圆形指示灯**(开=实心圆/反白,关=空心环)。数值仍写出文本读数(bullet 原则:别只靠弧线)。
- **minimal(瑞士极简)**:**大留白 + 超大数字 + 只用 1px 发丝线分隔**,近乎无装饰、无填充块、无图标(或极弱)。激活态靠**字重 + 一条短粗下划线**或反白一个小点,层级全靠字号与空白(字号阶到 104)。实体墙做成发丝线网格,每格超大 value/state_text + 极小 name。
- **newspaper(报纸)**:**多栏密排**,粗报头 nameplate + 栏线分隔,小字密排,标题纯黑粗体。实体做成"分类信息条"或小栏目块;激活态用**纯黑粗体 + 实心小方块**,关态常规字重。柱状/大块用斜线网点。
- **terminal(TUI/命令行)**:**等宽 + 窗口边框 + ASCII 分隔线**。实体做成**列表行或带边框的字符块**:`[●] 客厅吸顶灯        ON`、`[ ] 走廊人体        无人`、sensor 用 `客厅湿度  48.0%` 对齐排版。激活态用**反白标题条/实心方块字符 `█` / `[●]`**,关态 `[ ]`。大块黑只用在细标题条,别整屏。

> 不确定某风格细节时,**打开它的 `home.html`/`device.html` 抄手法**(它怎么画卡片/进度条/标题,你就怎么画实体)。保持与该套其它页一眼同源。

## 6. 验收 & 测试

**渲染冒烟(必须)**:`tests/test_render_smoke.py` 现在只测 `style_a`。本任务完成后,**让冒烟覆盖所有风格的 ha 页**——二选一:
- (推荐)把 `test_render_all_pages_smoke` 参数化成"遍历 `styles.list_styles()` × 该风格 `has_page` 的页",对每套每页用 `empty_context()` 渲染,断言出图、尺寸 `(rc.height, rc.width)`、灰度 `L`、不报错;
- 或至少新增一个"遍历 6 套风格渲染 ha 页"的用例。

**人工出图自检(必须,像基准版那样)**:用下面这份**静态样例卡片**(不打网络)给每套风格渲染一张 PNG 看效果,确认:① 网格列数自适应正确(12 张→4 列)② 开/关一眼能分 ③ sensor 显 value+unit、其它显 state_text、climate/media 有 sub ④ 风格观感与该套其它页同源 ⑤ 铺满不空、无大块实心黑。

```python
import sys; sys.path.insert(0, '.')
from server.render import styles, pipeline
from server.render.contract import empty_context
ctx = empty_context()
ctx['ha'] = {'cards': [
  {'name':'客厅吸顶灯','kind':'toggle','icon':'mdi:lightbulb','on':True,'state_text':'开','value':'','unit':'','sub':''},
  {'name':'客厅湿度','kind':'sensor','icon':'mdi:water-percent','on':False,'state_text':'','value':'48.0','unit':'%','sub':''},
  {'name':'主卧空调','kind':'climate','icon':'mdi:thermostat','on':True,'state_text':'制冷','value':'24.5','unit':'','sub':'目标 26.0°'},
  {'name':'餐厅窗帘','kind':'cover','icon':'mdi:window-shutter','on':True,'state_text':'100%','value':'','unit':'','sub':''},
  {'name':'次卧窗帘','kind':'cover','icon':'mdi:window-shutter','on':False,'state_text':'0%','value':'','unit':'','sub':''},
  {'name':'餐厅新风机','kind':'toggle','icon':'mdi:fan','on':True,'state_text':'开','value':'','unit':'','sub':''},
  {'name':'走廊人体','kind':'binary','icon':'mdi:motion-sensor','on':False,'state_text':'无人','value':'','unit':'','sub':''},
  {'name':'走廊烟雾','kind':'binary','icon':'mdi:smoke-detector','on':False,'state_text':'正常','value':'','unit':'','sub':''},
  {'name':'主卧空调功率','kind':'sensor','icon':'mdi:flash','on':False,'state_text':'','value':'75.0','unit':'W','sub':''},
  {'name':'我的家','kind':'sensor','icon':'mdi:weather-partly-cloudy','on':False,'state_text':'','value':'18.4','unit':'°','sub':''},
  {'name':'加湿器','kind':'toggle','icon':'mdi:air-humidifier','on':False,'state_text':'关','value':'','unit':'','sub':''},
  {'name':'次卧温度','kind':'sensor','icon':'mdi:thermometer','on':False,'state_text':'','value':'29.0','unit':'°C','sub':''},
]}
rc = pipeline.RenderConfig(); rc.rotate = 0     # 横屏正立便于看
for s in ['bento','blueprint','gauge','minimal','newspaper','terminal']:
    open(f'/tmp/ha_{s}.png','wb').write(pipeline.render_html_to_png(styles.render_page(s,'ha',ctx), rc))
    print('rendered', s)
```

**回归**:`python3 -m pytest tests/ -q` 全绿(你只新增模板,不该影响其它测试;若参数化了冒烟,确认 6 套都过)。

## 7. 实现顺序建议

① 先做 **bento**(离 style_a 最近,验证数据/网格/图标复用链)→ ② 参数化冒烟测试 → ③ 再做差异大的 **gauge / minimal / terminal**(各自视觉语言重)→ ④ 补 **blueprint / newspaper** → ⑤ 6 套各出一张样例图自检,人工过一遍 §6 的 5 条。

---

**红线**:别动 Python/schema/契约/style_a;别打包字体;别用颜色区分 on/off;别让任何一套出现整屏大块实心黑。
