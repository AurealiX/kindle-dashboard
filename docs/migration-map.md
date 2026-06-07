# 搬运地图(老代码 → 新仓库)

> 老代码当配件箱:整块搬的去硬编码+参数化,该重写的重写,该丢的丢。
> 源:`/mnt/work/kindle/kindle-dashboard/`(看板)、`/mnt/work/kindle/ccusage-web/`(用量)。
> **绝不复制旧 git 历史**(防密钥泄漏)。

## A. 整块搬运 + 参数化(核心资产)

| 老文件 | 新位置 | 搬运动作 / 要去掉的硬编码 |
|---|---|---|
| `app/main.py` | `server/` | 30s 渲染循环 + `/api/*` 接收端点。端口、轮播间隔、启用页面改为读配置 |
| `app/data_prep.py` | `server/` + `server/sources/` | 统一数据准备管线;按数据源拆进 `sources/`,每源一文件 |
| `app/html_render.py` | `server/render/` | Chromium 截图 + PIL 旋转灰度。**保留** `_kill_stale_chrome()`、`--no-crashpad`、部分失败保留旧页逻辑 |
| `app/styles.py` | `server/render/` | 风格调度。`STYLES`/`PAGE_FILES` 改为从配置/风格包目录扫描,不写死 |
| `app/templates/style_a/*` | `styles/style_a/` | 五页杂志风模板 + CSS,作为内置风格包 A |
| `kindle/start.sh` | `installers/kindle/` | **保留** 杀 pmond 顺序、fbink 刷屏、`ensure_wifi()` 看门狗、nohup;服务地址改为安装时注入 |
| `kindle/stop.sh` | `installers/kindle/` | 直接搬 |
| `mac/read_reminders.js` | `installers/macos/reminders/` | JXA 读提醒事项,逻辑不变。**落点改 installers**:它是 Mac 端"自采自推"agent,不走 `server/sources/` 采集器接口。✅已搬 |
| `mac/codex_quota.py` | `server/sources/` | 调 `wham/usage`。代理地址、token 路径参数化 |
| `mac/collect_mac.sh` | `server/sources/` | Mac 指标采集(top/sysctl/vm_stat) |
| `mac/sync_reminders.sh` + `*.plist` | `installers/macos/reminders/` + install.sh 生成 plist | ✅已搬。`NAS_URL` 硬编码 → 改 `KINDLE_SYNC_URL` 环境变量(launchd 注入本机端口);install.sh 按 `reminders.enabled` 条件装,uninstall.sh 移除 |
| `mac/sync_*.sh`(其余) + `*.plist` | `installers/macos/` | launchd 模板,路径/地址安装时注入。开头 `export PATH` 必保留 |
| `agent/collect_nas.py` | `server/sources/` | Linux `/proc` 采集 |
| `agent/*.service` `*.timer` | `installers/nas/` | systemd 模板,参数化 |
| `ccusage-web/server.js` | **不搬(已弃用)** | ccusage-web 是旧局域网临时中间件,本项目不要。改为本机直接跑 ccusage CLI(`server/sources/ccusage_cli.py`)。 |
| `fonts/NotoSansCJK-*.ttc` | `styles/` 或 `server/render/` | 中文字体,直接搬 |
| `Dockerfile` `docker-compose.yml` | `installers/nas/` | **环境变量里的所有凭据删光**,改为挂载 config.yaml |

## B. 全新写(没有可搬的)
- `server/config/` —— 配置 schema + 默认值 + 加载/校验/热重载
- `web/` —— 设置网页(读写 config.yaml)
- `installers/macos/` `installers/nas/` `installers/kindle/` —— 一键安装脚本
- 风格包系统(数据/模板解耦的抽象层)

## C. 绝不带走(明确丢弃)
- **任何凭据**:`docker-compose.yml` 里的 `QWEATHER_KEY` / `HA_TOKEN` / `PRINTER_PREFIX`,所有内网 IP、SSH 账号密码
- 旧 PIL 手绘渲染:`app/renderer.py` `renderer_ai.py` `renderer_device.py`
- 废弃硬件支线:`esp32-firmware/`、`app/templates/esp32/`
- `.DS_Store`(所有目录)、`__pycache__/`
- 旧 git 历史

## D. 待搬运时确认的细节
- 字体放 `styles/`(每风格自带)还是 `server/render/`(全局共享)?倾向全局共享。
- 打印机卡片要从"拓竹专属"抽象成"任意 HA 实体卡片"(降品牌绑定),搬 `printer.html` 时做。
