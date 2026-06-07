# 施工图:多 Kindle 分辨率适配

> **交付对象**:接手的开发 AI。本文自包含,读完即可独立施工,无需追问。
> **状态**:✅ **已实现(2026-06-07)**。spike 实测 `--force-device-scale-factor=<小数>` 在本机 google-chrome headless 生效且锐利 → 走方案 A,风格 CSS 零改动。落地在 `pipeline.py`(`BASE_W/H` 常量 + scale + letterbox)、`schema.py`(`KINDLE_MODELS` + `resolve_render_size` + `kindle_model` 下拉)、`web/setup.html`(机型↔自定义宽高联动)、`tests/test_multi_resolution.py`。本文保留作设计依据。
> **铁律**:遵守仓库三铁律(零硬编码 / 配置即页面 / 诚实降级)。新增可配置项 = 先改 `server/config/schema.py` 再改代码。

---

## 1. 要解决什么

现在看板固定按 **800×600 横屏**渲染,旋转成 **600×800 竖屏**写墨水屏 —— 只适配基础款 6 寸 Kindle(600×800)。Paperwhite / Oasis / Scribe 等高 PPI 机型分辨率高得多,直接拉这张 600×800 的图会**糊**(被 Kindle 端放大,字发虚)。

目标:**用户填一次自己 Kindle 的分辨率(或选机型),服务端就按原生分辨率出清晰的图,不糊、不留大块黑边。风格作者依然只针对一块固定画布设计,不用关心分辨率。**

---

## 2. 现状(已经做好的一半,别重复造)

尺寸/旋转/灰度**早已参数化**,不是写死的:

| 位置 | 现状 |
|---|---|
| `server/config/schema.py` L65-69 | `render_width=800` `render_height=600` `render_rotate=270` `render_grayscale=True` 已是配置项 |
| `server/render/pipeline.py` `RenderConfig` | 从 `server.render_*` 读这四个值 |
| `pipeline.py` `_shot_to_image()` L106-123 | Chrome `--window-size={width},{height}` 截图 → crop 到 width×height → 灰度 |
| `pipeline.py` `render_html_to_png()` L126-134 | 按 `rotate` 旋转输出 |

**真正的瓶颈有两个**:

1. **CSS 把画布写死成 800×600 物理像素**
   - `styles/style_a/style.css` L16:`html,body{width:800px;height:600px;}`
   - 各模板里全是绝对像素:`.col-cal{width:368px}`、字号 `66px`/`62px`、padding `22px 30px`……
   - 后果:就算把 `render_width` 改成 1648,Chrome 窗口变大了,但 body 还是 800×600,**右下角一大片空白**,内容不会铺满。

2. **`--force-device-scale-factor=1` 硬编码**
   - `pipeline.py` L110 写死 `=1`,等于强制"1 CSS 像素 = 1 物理像素",放弃了高分屏的清晰度红利。

所以本任务**不是**"把所有 CSS 改成响应式"(那是噩梦,且要对 10 套风格各做一遍),而是 ——

---

## 3. 关键洞察:Kindle 几乎全是 3:4,基准画布等比缩放即可

实测主流机型分辨率(竖屏 W×H):

| 机型 | 竖屏分辨率 | 比例 W/H | PPI |
|---|---|---|---|
| Kindle 基础版(8/10/11 代) | 600×800 | 0.750 | 167 |
| Paperwhite 3/4、Voyage | 1072×1448 | 0.740 | 300 |
| Paperwhite 5(11 代 6.8") | 1236×1648 | 0.750 | 300 |
| Paperwhite 12 代(7")、Oasis 2/3、Colorsoft | 1264×1680 | 0.752 | 300 |
| Scribe(10.2") | 1860×2480 | 0.750 | 300 |

**全部 ≈ 3:4(竖)= 4:3(横)**,而现有基准横屏 800×600 正好 = 4:3。
→ 结论:**等比放大基准画布就能覆盖几乎所有机型**,长宽比误差最大 ~1.3%(PW3/4),可忽略或微留白兜底。**不需要重做布局。**

---

## 4. 推荐方案:基准画布 + device-scale-factor 等比放大

**一句话**:风格永远只针对 **基准画布 800×600(横屏)** 设计;渲染时算出 `scale = 目标横屏宽 / 基准宽`,用 Chrome 的 `--force-device-scale-factor=scale` 让浏览器把同一份 800×600 的 CSS 布局**矢量级放大**成目标物理分辨率的位图(字体是矢量,放大后依然锐利;斜线 hatch 同比放大)。

### 为什么是这个,不是别的

| 方案 | 评价 |
|---|---|
| **A. device-scale-factor(本方案)** | ✅ 模板/CSS **零改动**,10 套风格全部免费受益;字体矢量放大锐利;只动渲染层一处。**选它** |
| B. `transform: scale()` 包一层 | 可行但要给每个模板注入 wrapper,且 e-ink 对 transform 子像素渲染偶有毛刺;不如 device-scale-factor 原生 |
| C. 全面响应式(vw/vh/clamp/容器查询) | ❌ 工作量爆炸,每套风格每个数字都要改;小屏响应式难调;与"批量出 10 套风格"严重冲突 |

### 数据模型改动:区分"基准画布"和"输出分辨率"

把现在含义混淆的 `render_width/height` 拆成两层概念:

- **基准画布 `base_width=800, base_height=600`**(横屏):风格设计的逻辑坐标系,**常量,不开放给用户改**(改了等于让所有风格重画)。放在代码常量或 schema 里标 `hidden`。
- **输出分辨率 `render_width/height`**:用户的 Kindle **横屏**物理像素(竖屏分辨率转横屏,即 H×W;如 PW5 竖 1236×1648 → 横 1648×1236,填 `render_width=1648, render_height=1236`)。

`scale = render_width / base_width`(用长边算;若 `render_height/base_height` 不一致说明比例不同,见下"非 4:3 兜底")。

### pipeline.py 具体改法

`_shot_to_image()`(当前 L106-123):

```python
scale = rc.render_width / rc.base_width        # e.g. 1648/800 = 2.06
subprocess.run([
    chrome, "--headless", "--no-sandbox", "--disable-gpu",
    "--no-crashpad", "--disable-crash-reporter",
    "--disable-dev-shm-usage", "--hide-scrollbars",
    f"--force-device-scale-factor={scale}",     # ← 从写死 1 改成算出来的
    f"--window-size={rc.base_width},{rc.base_height}",  # ← 窗口永远是基准 800×600(CSS 像素)
    "--default-background-color=FFFFFFFF",
    f"--screenshot={png_path}", f"file://{html_path}",
], ...)
# 截图产物现在是 base*scale 物理像素 ≈ render_width × render_height
img = Image.open(png_path).convert(mode)
# crop 到真正的输出尺寸(scale 取整可能差 1~2 px,用 render_width/height 兜准)
img = img.crop((0, 0, rc.render_width, rc.render_height))
# 若实际产物比目标小(非整数 scale),先 letterbox 补白再 crop,避免越界——见下
```

**注意**:`device-scale-factor` 接受小数(2.06 合法)。但产物像素 = round(base × scale),与 `render_width` 可能差 1~2 px。crop 前判断尺寸,不足则在白底上居中,**绝不报错**(诚实降级)。

旋转/灰度逻辑(`render_html_to_png` L126-134)**完全不动** —— 旋转的是已经放大好的位图。

### 非 4:3 机型兜底(诚实降级,别崩)

若 `render_width/base_width ≠ render_height/base_height`(比例不是 4:3):
- `scale` 取 **min(宽比, 高比)**(等比缩放,保证内容完整不裁切)
- 短边方向产生的空白用**白底居中**(letterbox),不拉伸变形
- 这是少数派机型的可接受妥协;真要像素级铺满,留给 P2 风格层为该比例单独出变体

---

## 5. 配置 & 设置页改动(零硬编码 + 配置即页面)

### schema.py
- 加 `base_width=800` `base_height=600`,标 `hidden=True`(内部基准,不给用户瞎改)。或作为代码常量 `BASE_W/BASE_H`,RenderConfig 读它 —— 二选一,倾向 schema hidden 以保持"一处定义"。
- `render_width/height` 的 label/help 改清楚:**"你的 Kindle 横屏分辨率(竖屏宽高对调)"**。
- **强烈建议加一个"机型预设"下拉**(体验,符合"非科班用户照 README 能成"):
  - 新增 `kindle_model` enum 字段,选项 = 第 3 节那张表(基础版/PW3-4/PW5/PW12-Oasis/Scribe/自定义)。
  - 选了机型 → 自动回填 `render_width/height`(横屏值);选"自定义"才显示手填宽高。
  - 回填逻辑放设置页 JS(`web/setup.html`),映射表与第 3 节一致。**映射表是唯一数据源,别在多处复制**。

### 设置页(web/setup.html)
- 机型下拉 + 自定义宽高联动(选预设禁用/隐藏手填框)。
- 旁注一行:"6 寸基础版选第一个即可;不确定型号查机器背面或设置→设备信息。"

### 实时预览(/kindle/preview.png)
- 预览本来就走渲染管线,改完自动按新分辨率出图。确认预览 endpoint 仍 `rotate=0`(横屏正立给人看),分辨率跟随配置。

---

## 6. Kindle 端要不要改?(基本不用)

Kindle 端 `start.sh` 用 `fbink` 把 PNG 居中刷屏,**fbink 按图实际尺寸贴**,只要服务端出的图 = 屏幕原生分辨率就严丝合缝。无需改 `installers/kindle/`。
（边缘情况:个别机型 fbink 需要 `-g` 指定区域,真机若发现偏移再说,**不在本任务范围**。）

---

## 7. 验收标准

1. 配置 `render_width/height` = 1648×1236(PW5 横屏),`/kindle/preview.png` 出的是 **1648×1236 锐利**横屏图,内容铺满、字不糊、无右下空白。
2. 旋转后 `/kindle/frame.png` = **1236×1648 竖屏**,可直接 fbink 上 PW5。
3. 默认配置(800×600)行为**与现在像素级一致**(scale=1,回归不破)。
4. 选"基础版"机型预设 → 自动填 600×800 竖→横 800×600,出图同现状。
5. 非 4:3 假设值(如手填 1000×600)→ letterbox 居中、不崩、不变形。
6. `python3 -m pytest tests/ -q` 全绿;**新增**:不同 scale 下渲染产物尺寸正确 + 默认值回归测试。
7. **style_a 的 CSS / 模板一个字没改**(证明方案 A 成立)。

---

## 8. 第一步:先做 spike 验证(别盲写)

`--force-device-scale-factor=<小数>` 在当前 headless Chromium(本仓用的是系统 Chrome 或 playwright chromium,见 `find_chrome()`)下,`--screenshot` 产物是否真按 `base × scale` 放大像素、字体是否矢量锐利 —— **headless old/new 模式行为有差异,先用一条命令在本机验证**:

```bash
# 造个 800×600 的测试页,scale=2,看产物是不是 1600×1200 且清晰
chrome --headless --force-device-scale-factor=2 --window-size=800,600 \
  --screenshot=/tmp/t.png file:///path/to/test.html
python3 -c "from PIL import Image; print(Image.open('/tmp/t.png').size)"  # 期望 (1600,1200)
```

- 若产物尺寸/清晰度符合预期 → 按第 4 节实现。
- 若 headless 忽略 device-scale-factor(某些版本如此)→ 退回**方案 B**(模板外包 `transform:scale(k)` wrapper,窗口设为目标尺寸),验收标准不变。**把实测结论记进 `CLAUDE.md` 已知坑。**

---

## 9. 范围边界(不做什么)

- ❌ 不重写任何风格的 CSS 成响应式(方案 A 的全部价值就在于不动它们)。
- ❌ 不做 Kindle 端 fbink 区域适配(除非真机发现偏移)。
- ❌ 不追求非 4:3 机型像素级铺满(letterbox 即可,完美适配归 P2 风格变体)。
- ❌ 不碰旋转/灰度/数据契约/数据源 —— 本任务只在"基准画布 → 物理位图"这一层做缩放。

---

## 10. 涉及文件汇总

| 文件 | 改动 |
|---|---|
| `server/config/schema.py` | +`base_width/height`(hidden 或常量)、+`kindle_model` 预设枚举、render_width/height 文案 |
| `server/render/pipeline.py` | `RenderConfig` 加 base_*;`_shot_to_image()` 算 scale、改 device-scale-factor、crop/letterbox |
| `web/setup.html` | 机型下拉 ↔ 自定义宽高联动(映射表 = 第 3 节) |
| `tests/` | +多分辨率渲染尺寸测试、默认值回归 |
| `docs/install.md` | "渲染/分辨率"一节:如何选机型、非 4:3 说明 |
| `CLAUDE.md` 已知坑 | 记 spike 实测结论(device-scale-factor 在本环境是否生效) |
| `docs/data-contract.md` | 若 base 画布概念影响契约描述则同步;预计不影响 |

完成后回写本仓 `CLAUDE_TASK_QUEUE.md`「待排期」第 3 项状态。
