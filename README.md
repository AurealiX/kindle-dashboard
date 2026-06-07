# Kindle Dashboard

> 把越狱的 Kindle 变成可配置的家庭信息看板 —— 两条命令 + 一个网页设置,不写代码。

⚠️ **越狱免责**:越狱有风险。本项目**不含**越狱工具,只负责越狱**之后**的部分。
🔒 **凭据安全**:你填的天气 Key / HA Token / SSH 账号**只存本地**(`config.yaml`),不上传任何服务器。

---

## 这是什么

Kindle 当瘦客户端,只定时拉一张渲染好的 PNG 刷上屏;采集、聚合、渲染全在一台常开电脑(Mac/NAS)上完成。

```
各数据源 → 常开电脑上的服务(采集+Chromium渲染 PNG)→ Kindle 每 20s 拉图显示
```

- 天气、提醒事项、AI 用量、设备监控(Win/Linux/Mac)、智能家居实体墙、3D 打印机(后两者经 Home Assistant)
- **配置化**:所有 IP/密钥/页面/风格从网页设置读,代码里不写死
- **配置即页面**:填了哪个数据源才显示对应页,没填自动隐藏
- **诚实降级**:缺数据显示占位,不报错、不白屏

## 前置要求

- 一台**常开**的 Mac(P0;NAS/Docker 见 P1)
- 已安装 **Chrome 或 Chromium**(渲染用):`brew install --cask google-chrome`
- 一台**已越狱**且**已开启 USBNetwork(SSH)**的 Kindle(本项目不含越狱工具)

## 快速开始(Mac)

### 1. 装服务

```bash
git clone <repo> kindle-dashboard && cd kindle-dashboard
bash installers/macos/install.sh
```

脚本会:建虚拟环境装依赖、从示例生成 `config.yaml`、装 launchd 开机自启、启动服务。
完成后会打印你的设置页地址和 Kindle 拉图地址。

### 2. 网页设置

浏览器打开 **`http://localhost:8585/setup`**,按模块填:

- **天气**:和风天气 QWeather 的 Key + 城市 ID
- **设备监控**:加要监控的机器(本机直读 / 推 / 拉),可重命名、勾选显示项
- **Home Assistant**:地址 + 令牌(填了才出打印机 / 智能家居页)
- **页面与风格**:选风格,右侧**实时预览**所见即所得

保存即生效,服务热重载,下一轮渲染应用新配置。

### 3. 配 Kindle

把 Kindle 用数据线连到 Mac(已开 USBNetwork),然后:

```bash
sh installers/kindle/detect.sh          # 先确认能识别到 Kindle
sh installers/kindle/install.sh         # 会问刷新间隔，再推送脚本 + 开机自启 + 启动显示
```

Kindle 开始显示看板(**横放**,顶边朝右)。之后改配置在网页保存即可,**Kindle 侧不用再碰**。

## 不想用了(一键还原)

```bash
sh installers/kindle/uninstall.sh       # 还原 Kindle:停看板、移除自启、删脚本、恢复界面
bash installers/macos/uninstall.sh      # 停 Mac 服务(加 --purge 删 venv/数据)
```

## 数据源一览

| 页面 | 数据源 | 需要 |
|---|---|---|
| 天气/首页 | 和风天气 QWeather | API Key + 城市 ID |
| 提醒事项 | 苹果提醒事项 | 一台 Mac 跑采集脚本推送 |
| AI 用量 | ccusage | 装了 ccusage 的机器 |
| 设备监控 | Win/Linux/Mac | 本机直读 / 推 agent / SSH 拉 |
| 智能家居 | Home Assistant 实体 | HA 地址 + 令牌,网页选实体 |
| 3D 打印机 | 拓竹(经 Home Assistant) | HA 地址 + 令牌 |

详见 [docs/install.md](docs/install.md)(详细步骤 + 故障排查)、[数据契约](docs/data-contract.md)、[搬运地图](docs/migration-map.md)。

## 状态与路线

✅ **P0(Mac 版)核心闭环真机验证通过**(Mac 装服务 / 网页配置预览 / Kindle 一键上屏 / 一键还原,均在真机跑通)。
🚧 安装体验升级(playwright 内置渲染引擎、ccusage 一键启用、macOS 菜单栏)代码完成,待 Mac 真机验证。
路线:**P0 Mac → P1 NAS Docker → P2 风格系统 → P3 扩展**。

风格做成「数据契约 + 风格包」解耦:所有风格引用同一套[数据契约](docs/data-contract.md),网页下拉切换 + 实时预览。已内置 **7 套皮肤**(`style_a` 杂志风 + `terminal`/`bento`/`blueprint`/`minimal`/`newspaper`/`gauge`),每套覆盖全部页面。**多分辨率已落地**:设置页选 Kindle 机型即按原生分辨率出清晰图(基础版/Paperwhite/Oasis/Scribe…),风格只按基准画布 800×600 设计,详见 [docs/multi-resolution-spec.md](docs/multi-resolution-spec.md)。新增风格见 [docs/style-authoring.md](docs/style-authoring.md)。

## License

本项目以 **MIT 许可证**开源,见 [LICENSE](LICENSE)。可自由使用、修改、商用,保留版权署名即可;软件按「原样」提供、不担保、作者不担责。
