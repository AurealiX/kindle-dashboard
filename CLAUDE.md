# Kindle Dashboard (开源版) — 项目约定

> 本文件是新仓库的最高约束。动手前必读。需要调整约定时**先改本文档,再改实践**。

## 项目目标(一句话)
让任何人不写代码,**两条命令 + 一个网页设置**,就能把越狱的 Kindle 变成可配置的家庭信息看板。

## 三条铁律(任何代码都不得违反)
1. **零硬编码** —— 所有 IP、密钥、城市、设备、页面、风格,全部从配置读,代码里不写死任何用户数据。新增可配置项 = 先改 schema,再改代码。
2. **配置即页面** —— 页面内容由配置决定:填了 HA 令牌才出打印机/设备页,填了天气 Key 才出天气页,没填的页自动隐藏,不报错。
3. **诚实降级** —— 缺数据的卡片显示占位符(`--` 或"未配置"),绝不抛错、绝不空白全屏。一个数据源挂掉不影响其他源。

## 仓库结构
```
server/            渲染+采集服务(Python / FastAPI)
  app.py / run.py  FastAPI 主服务 / 启动入口(读 config 端口,绑 0.0.0.0)
  menubar.py       macOS 菜单栏(rumps:状态●/○ + 打开设置/启停/退出,登录自启)
  render/          渲染管线 + 风格调度(HTML→Chromium→PIL 旋转灰度)
  sources/         各数据源采集器(weather/homeassistant/ccusage/ccusage_cli/metrics),一源一文件
    collectors/    跨平台设备采集脚本(collect_linux/macos/windows),本机/SSH拉/推agent 三处复用
  config/          配置 schema + 默认值 + 加载/校验/热重载
web/               配置网页(setup UI),读写 config.yaml
installers/
  macos/           Mac 一键安装(install/uninstall/restart)+ reminders/(提醒同步 agent)
                   + quota/(Claude/Codex 额度采集:claude_statusline/codex_quota/sync)+ enable/disable_{reminders,quota}.sh
  nas/             docker-compose + 安装脚本(P1)
  kindle/          Kindle 一键配置(detect/install/uninstall + 端侧 start/stop)
styles/            预设风格包(一套 = 模板 + CSS + preview 图)
docs/              安装指南 / 架构 / 数据源接入说明 / 搬运地图
config.yaml        ← 用户真实配置,**本地生成,不入库**(见 .gitignore)
```

## 配置层约定(P0 第一块)
- **格式 = YAML**(人类可读,设置网页读写都方便)。单文件 `config.yaml`。
- **schema 与默认值** 放 `server/config/`。schema 是唯一真相源:页面有哪些字段、哪些必填、默认值多少,全在这里。
- **加载流程**:启动读 `config.yaml` → 按 schema 校验 → 缺项用默认值 → 缺关键凭据的模块自动禁用(对应页面隐藏)。
- **热重载**:设置网页保存即写 `config.yaml`,服务下一轮渲染读取新值,不重启。
- **凭据只存本地**:HA token / 天气 Key / SSH 账号写进 `config.yaml`,该文件在 `.gitignore` 里,网页 UI 上要明示"只存本地、不上传"。

## 数据源约定
- 每个数据源 = `server/sources/` 下一个独立模块,统一接口(给定配置 → 返回标准化数据 dict,失败返回降级占位)。
- 三种采集范式(沿用现状,文档化):**服务端直采**(天气)、**借中枢拉取**(HA→打印机/设备)、**自采自推**(提醒事项/ccusage/额度,远端 POST 进来)。
- **设备监控已定方案**:本机直读 `/proc`/系统命令;远程机器在设置网页二选一 —— **推**(目标机跑一行装 agent,不交密码)或 **拉**(填 SSH 账号,目标机零安装)。每台远程机各自选。

## 渲染约定
- 模板按 **800×600 横屏**设计,Chromium 截图后 **PIL 旋转成 600×800 灰度 PNG**。
- **风格包解耦**:数据(context dict)与模板(风格包)分离,换风格不动数据层。一套风格 = `styles/<name>/` 下的模板 + CSS + preview。
- 渲染纪律:铺满不留大块白;大色块用斜线填充代替实心黑;数据少的页不硬撑多列。
- Jinja2 无 `zfill`,补零用 `{{ "%02d"|format(x) }}`。

## 搬运纪律(老代码 = 配件箱,不是地基)
老代码只读参考:`/mnt/work/kindle/kindle-dashboard/`(看板)、`/mnt/work/kindle/ccusage-web/`(用量)。详见 `docs/migration-map.md`。
- **整块搬+参数化**:渲染管线(含 `init:true`/`--no-crashpad`/僵尸清理/部分失败保留旧页)、Kindle `start.sh`(杀 pmond 顺序/fbink/WiFi 看门狗/`@reboot`)、各数据源对接逻辑。
- **全新写**:配置层、设置网页、安装器、风格包系统。
- **绝不带走**:任何私钥/token/内网 IP/密码、废弃 ESP32 支线、旧 PIL 渲染(`renderer*.py`)、重复 mac-sync、`.DS_Store`、**旧 git 历史(防密钥泄漏)**。

## 已知坑(必须内建解决)
- Chromium 僵尸进程 → Compose `init: true` + Chromium `--no-crashpad` + 代码层 `_kill_stale_chrome()`。
- 渲染部分失败 → 只更新成功的页、保留旧页;全部失败则不覆盖并杀僵尸。
- ccusage 命令必须带 `--timezone Asia/Shanghai`,否则按本机时区切天。
- Mac launchd 环境无 PATH → 脚本开头 `export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"`。
- 拓竹 `remaining_time` 单位是**小时**不是分钟。
- 额度数据来源两类别混:**Codex `wham/usage` 是非公开后端接口**,无文档、官方一改即失效(文档要标注、降级兜底);**Claude 额度走 statusLine 是官方公开机制(稳)**——Claude Code 主动把 `rate_limits` 从 stdin 喂给状态栏命令,不是逆向。
- **多分辨率(2026-06-07 spike 实测)**:`--force-device-scale-factor=<小数>` 在本环境 `/usr/bin/google-chrome` headless 下**生效且锐利**(800×600 @ 2.06 → 精确 1648×1236,字体矢量放大不糊)→ 采用方案 A(基准画布 800×600 + device-scale-factor 等比放大,风格 CSS 零改动),**未走方案 B**。基准画布是常量 `pipeline.BASE_W/BASE_H`;机型→分辨率映射唯一源在 `schema.KINDLE_MODELS`;非 4:3 用白底 letterbox 兜底。

### 安装/真机坑(2026-06-07 真机验证发现,已修进脚本)
- **macOS 系统 python(3.9)venv 不支持 `--copies`** → 用普通 `python3 -m venv`;网络盘(/Volumes)的 symlink 问题靠"复制到本地盘"解决,不是靠 --copies。
- **改 Kindle `/etc/crontab/root` 等系统分区**:`mntroot rw` 必须用**全路径 `/usr/sbin/mntroot`**(非交互 SSH 的 PATH 不含 /usr/sbin,裸命令静默失败→只读写不进)。
- **SSH 启动 Kindle 端 start.sh 用 `setsid`**(`nohup` 扛不住 SSH/ControlMaster 关闭被收走);cron `@reboot` 启动则 nohup 够。
- **Kindle busybox `ps` 不显完整命令行** → 判断进程死活用 `/proc/$PID` 或 dashboard.pid,别 `ps|grep`。
- **USBNetwork**:Mac 端 USB 网卡要配 `192.168.15.201/24` 才能连 Kindle `192.168.15.244`(install.sh 自动检测接口配,带就绪重试)。
- **Kindle root 密码**越狱默认 `mario`,用户可能改过(install 运行时已提示)。
- **渲染引擎**:不再硬依赖系统 Chrome —— find_chrome 也探测 playwright 自带 chromium(install 询问自动下载,不依赖 brew)。

## 开发流程
- 路线:**P0 Mac → P1 NAS Docker → P2 风格系统 → P3 扩展**。当前在 P0。
- 会话开始读 `CLAUDE_TASK_QUEUE.md`。
- 改 bug 先写失败测试复现。改完主动跑验证。
- 测试放 `tests/`,跑:`python3 -m pytest tests/ -q`(单文件也可 `python3 tests/xxx.py` 直接跑)。
- 大改动前先出 Plan,确认后动手。

## License / 免责(开源前定稿)
- License:**MIT**(已定 2026-06-07,见仓库根 `LICENSE`,版权 2026 yizhixiaoheigou)。
- README 顶部声明:越狱有风险、本项目不含越狱工具、只负责越狱之后的部分。
- 凭据安全声明:配置只存本地、不上传。
