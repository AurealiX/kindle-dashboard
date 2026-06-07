# 接入设计:Microsoft To Do 作为可选提醒事项源(方案 B / 网页登录)

> **✅ 实现状态(2026-06-07):已实现并测试通过。** 代码见 `server/sources/mstodo.py`、`server/app.py`
> (mstodo 进 SOURCES + 4 个 `/api/mstodo/*` 端点)、`server/config/schema.py`(mstodo 段)、
> `server/render/build_context.py`(合并一行)、`web/setup.html`(登录卡片)、`tests/test_mstodo.py`(10 项)。
> **当前内置微软公开 client_id(方案甲,免注册);**升级到自有应用见 §6b,代码无需改、只换 client_id 默认值。
> 本文档保留为设计依据 + 维护者升级指南。
>
> 原始定位:给实现者看的施工图,已对齐 `CLAUDE.md`(三铁律)与 `docs/data-contract.md`(数据契约)。

## 1. 目标(一句话)
让使用 Microsoft To Do 的用户,在设置网页点一个按钮登录微软账号,就能把自己的 To Do 待办拉进看板,**和已有的 Apple 提醒事项合并显示**。默认关闭,不用的人零感知。

## 2. 为什么这么做 / 与现状的关系
- 现状提醒事项只有一条链路:Mac 读 Apple 提醒 → POST `/api/apple-sync` → `cache["reminders"]`(自采自推范式)。
- MS To Do 是**服务端直采**范式(像 weather):服务器用 refresh token 定时拉 Microsoft Graph API。
- 两源**独立存放、渲染时合并**,谁挂都不影响谁(诚实降级)。

## 3. 三铁律对照(实现时不得违反)
1. **零硬编码**:开关、client_id、可选项全进 schema;不写死任何用户数据。
2. **配置即页面**:没启用 mstodo、没登录 → 该源静默返回空,home 页不因它报错;启用并登录后才有数据。
3. **诚实降级**:token 失效/网络错/API 报错 → 该源返回 `None`,Apple 提醒照常显示,卡片不空屏不抛错。

## 4. 数据流总览
```
[设置网页] 点"连接 Microsoft To Do"
   → POST /api/mstodo/login/start      (服务器向微软申请设备码)
   → 网页显示 verification_uri + user_code
   → 用户在浏览器授权(用自己的微软账号)
   → 网页轮询 GET /api/mstodo/login/status
   → 成功:服务器把 token 写入 data/mstodo_token.json,置 mstodo.enabled=true

[每轮采集] collect_all()
   → sources/mstodo.collect(cfg)
       → 读 data/mstodo_token.json
       → access_token 过期则用 refresh_token 换新(并轮换保存)
       → GET /me/todo/lists  →  逐列表 GET .../tasks(处理分页)
       → 归一化为标准字段
       → 返回 {"reminders_mstodo": [...], "mstodo_updated": "<iso>"}

[渲染] prep_context()
   → reminders = cache["reminders"](Apple) + cache["reminders_mstodo"](MS)
   → 沿用现有分类逻辑(逾期/今天/将到期)
```

## 4b. 接入点:只进网页设置面板,不碰任何安装器(重要)
MS To Do 是**服务端直采**,与苹果提醒(自采自推)的部署模型根本不同,实现时务必分清,别照抄苹果提醒的安装逻辑:

| | 苹果提醒事项 | Microsoft To Do |
|---|---|---|
| 采集范式 | 自采自推:Mac 本地读 Reminders.app 推给服务 | 服务端直采:服务器自己调 Graph 云 API |
| 需要本机 agent | 要(macOS launchd 每 5min) | **不需要** |
| 需要在 install.sh 里装一步 | 要(装那个 launchd) | **不需要,零安装** |
| 需要系统授权弹窗 | 要(macOS 提醒事项权限) | **不需要**(走云,不碰本机数据) |
| NAS Docker 部署 | 不可用(无 Mac) | **可用,行为一致** |

结论:
- **不要**在 `installers/macos/install.sh`(或任何安装器)里加 MS To Do 的步骤、launchd、交互式询问。
- 启用 + 登录**全部在网页设置面板完成**(§7),装在 Mac 还是 NAS Docker 都一样,服务联网即可拉。
- 与之对照:install.sh 里 AI 用量是交互式询问、苹果提醒是读 `reminders.enabled` 后装 launchd——**这两种都不适用于 MS To Do**,它只需要网页登录写出 token 文件,服务下一轮自然生效。
- 因此 §11 装配清单里**没有**安装器改动,`docs/install.md` 也只是补一句"在设置页连接即可",无命令行步骤。

## 5. 凭据存储(关键设计)
- **token 不进 `config.yaml`**。config.yaml 只放开关和非敏感选项。
- refresh token / access token 存独立文件 **`data/mstodo_token.json`**,权限 `600`。
  - `data/` 已被 `.gitignore` 忽略(见现有 gitignore「运行时数据」段),**无需改 gitignore**,天然不入库。
- 文件结构:
  ```json
  {
    "client_id": "14d82eec-204b-4c2f-b7e8-296a70dab67e",
    "authority": "https://login.microsoftonline.com/consumers",
    "scope": "Tasks.Read offline_access openid profile",
    "refresh_token": "<敏感>",
    "access_token": "<敏感>",
    "access_token_exp": 1733570000,
    "account": "someone@outlook.com"
  }
  ```
- **任何日志/报错/接口响应都不得输出 token 字段内容。** 状态接口只回「已连接 / 账号名 / 列表数」这类非敏感信息。

## 6. 配置 schema 改动(`server/config/schema.py`)
新增一个 Section(放在现有 `reminders` 段附近):
```python
Section(
    key="mstodo", label="Microsoft To Do", page="home",
    help="可选。微软 To Do 待办,登录一次微软账号即可,数据与苹果提醒事项合并显示。",
    enable_when=["enabled"],
    fields=[
        Field("enabled", "启用", "bool", False, hidden=True),  # 由登录端点写入,不在网页手填
        Field("client_id", "应用 ID", "str", "<PROJECT_AZURE_CLIENT_ID>",
              help="项目自有的 Azure 应用 ID(已内置默认值,用户无需改;client_id 公开无密钥,可入库)。"
                   "进阶用户可填自己注册的应用 ID。"),
        Field("include_flagged_emails", "包含『标记的邮件』列表", "bool", False,
              help="Outlook 标记邮件会生成一个任务列表,默认不混入提醒事项。"),
    ],
),
```
同时把 home 页启用条件补上 mstodo(现状第 ~251 行):
```python
"home": enabled.get("weather") or enabled.get("reminders") or enabled.get("mstodo"),
```
> 注意 `enabled` 由登录成功后由后端写入 config,而非用户手填;UI 上这个开关展示登录状态、可"断开连接"。

## 6b. 登录用的 Azure 应用(决策:项目自有,维护者一次性注册)
**决策(2026-06-07):作为开源产品,用项目自己注册的 Azure 应用,不借微软公开客户端。**
这样用户授权时看到的应用名是「Kindle Dashboard」(正规、可控),而不是借来的「Microsoft Graph Command Line Tools」。

谁做什么,分清楚:
- **维护者(项目方)**:一次性注册一个 Azure 应用,把拿到的 `client_id` 填进 schema 默认值(替换 `<PROJECT_AZURE_CLIENT_ID>`)。`client_id` 是公开标识、**无密钥**,可以直接写进开源代码。全体用户共用这一个 ID(和 rclone / Thunderbird 等开源软件做法一致)。
- **终端用户**:**什么都不用获取**。不注册、不申请 Key、不碰 Azure。只在设置页点【连接】→ 用自己的微软账号登录 → 点【允许】。详见 §7.3 的用户体验。

### 维护者一次性注册步骤(约 10 分钟,只做一次)
1. 浏览器开 [portal.azure.com](https://portal.azure.com),用任意微软账号登录。
2. 搜索进入 **Microsoft Entra ID**(原 Azure AD)→ 左侧 **App registrations** → **New registration**。
3. 填写:
   - **Name**:`Kindle Dashboard`(← 这就是用户授权时看到的名字,起个体面的)
   - **Supported account types**:选 **"Accounts in any organizational directory and personal Microsoft accounts"**(必须含 personal,否则 outlook.com 个人号登不了)
   - **Redirect URI**:留空(设备码流程不需要)
   - 点 **Register**。
4. 注册后在 **Overview** 页复制 **Application (client) ID** —— 这就是要内置的 `client_id`。
5. 左侧 **Authentication** → 找到 **Allow public client flows** → 打开为 **Yes**(设备码流程必须开,否则登录报错)。保存。
6. 左侧 **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions** → 勾选 **`Tasks.Read`** 和 **`offline_access`**(后者用于拿 refresh token)→ Add。个人账号下 Tasks.Read 由用户自己同意,**无需管理员同意**。
7. (可选,后续打磨)Publisher verification 做了授权页会显示已验证发布者;不做也能用,个人账号只是没有"已验证"标记。

把第 4 步的 ID 填进 `server/config/schema.py` 的 `mstodo.client_id` 默认值即可。authority 用 `https://login.microsoftonline.com/common`(配合"任意组织+个人账号"类型)。

## 7. 设备码登录(方案 B,网页版)
个人微软账号(outlook.com)**只能走 delegated 设备码流程**,不能用纯后端密钥静默登录。流程做进设置网页。

### 7.1 后端端点(`server/app.py`)
- `POST /api/mstodo/login/start`
  - 向 `{authority}/oauth2/v2.0/devicecode` POST `client_id` + `scope`。
  - 服务端保存 `device_code`(**不返回给前端**),按一个随机 `session` 索引;启动后台线程轮询 token 端点。
  - 返回:`{session, user_code, verification_uri, expires_in, interval}`。
- `GET /api/mstodo/login/status?session=...`
  - 返回 `{state: "pending"|"success"|"error"|"expired", account?, lists?, error?}`。
  - `success` 时:服务器已把 token 写入 `data/mstodo_token.json`,并已置 `mstodo.enabled=true`(走现有 config 保存逻辑)。
- `POST /api/mstodo/logout`
  - 删除 `data/mstodo_token.json`,置 `mstodo.enabled=false`。
- 并发:同一时刻只允许一个进行中的登录会话;过期/完成即清理。

### 7.2 设备码流程细节
- 申请:`POST {authority}/oauth2/v2.0/devicecode`,body `client_id`、`scope`。
- 轮询:`POST {authority}/oauth2/v2.0/token`,body
  `grant_type=urn:ietf:params:oauth:grant-type:device_code`、`client_id`、`device_code`。
  - `error=authorization_pending` → 继续等(按 `interval` 秒)。
  - `error=slow_down` → `interval += 5`。
  - 拿到 `access_token` → 成功;连同 `refresh_token` 落盘。
  - 超过 `expires_in` 未授权 → `expired`。
- authority 默认 `https://login.microsoftonline.com/common`(配合自有应用的"任意组织+个人账号"类型,个人 outlook 与企业账号都能登)。若把应用注册成"仅个人账号",则用 `/consumers`。两者与 §6b 注册时选的 account type 必须一致。

### 7.3 前端(`web/setup.html`)—— 用户体验(零配置)
**核心:用户不需要获取任何 API/密钥,只用自己平时的微软账号登录一次。** 全流程:
```
设置页「Microsoft To Do」卡片 → 点【连接】
   → 网页显示:"用手机或电脑浏览器打开 <verification_uri>,输入代码 <user_code>"
     (verification_uri 做成可点链接、user_code 做成一键复制)
   → 用户打开该网址 → 用自己的 outlook 账号登录 → 看到「Kindle Dashboard 想读取你的任务」→ 点【允许】
   → 网页(轮询中)自动变:"✅ 已连接:<account>,N 个列表" + 【断开连接】按钮;顶部徽章变绿
   → 看板下一轮渲染即出现 To Do 待办
```
状态机:
- 未连接 → 按钮「连接 Microsoft To Do」。
- 点击 → 调 `start` → 展示 uri + code,按 `interval` 轮询 `status`。
- `success` → 显示账号 + 列表数 + 「断开连接」。
- `error/expired` → 提示重试(代码 15 分钟过期)。
- UI 明示一行:**「登录凭据只存本地,不上传任何服务器」**(对齐凭据安全声明)。
- 授权页显示的应用名是「Kindle Dashboard」(因为用的是项目自有应用,见 §6b)。

## 8. 采集器规格(`server/sources/mstodo.py`)
统一接口 `collect(cfg: dict) -> dict | None`(与 weather.py 一致)。

```
def collect(cfg):
    m = cfg.get("mstodo", {})
    if not m.get("enabled"): return None
    tok = load_token_file()                 # data/mstodo_token.json
    if not tok or not tok.get("refresh_token"): return None
    at = ensure_access_token(tok)            # 过期才刷新;刷新后轮换保存
    if not at: return None                   # 刷新失败 → 诚实降级
    lists = graph_get("/me/todo/lists", at)  # 真实列表(智能视图不在此返回)
    reminders = []
    for lst in lists["value"]:
        if lst.get("wellknownListName") == "flaggedEmails" and not m.get("include_flagged_emails"):
            continue
        for t in graph_get_all(f"/me/todo/lists/{lst['id']}/tasks", at):  # 处理 @odata.nextLink 分页
            reminders.append(normalize(t, lst))
    return {"reminders_mstodo": reminders, "mstodo_updated": now_iso()}
```

要点:
- **access token 缓存**:`ensure_access_token` 比对 `access_token_exp`,未过期直接用,过期才调 refresh grant(`grant_type=refresh_token`)。避免每轮渲染都打一次网络。
- **refresh token 轮换**:微软可能在刷新时返回新的 refresh_token。**只要响应里带 refresh_token 就覆盖保存**,否则下次刷新会失败。
- **分页**:`/tasks` 默认页大小有限,必须循环跟随 `@odata.nextLink` 直到取完。
- **超时/异常**:任何 httpx 异常或非 2xx → `print("[mstodo] ...")` 后返回 `None`,绝不抛到上层(`collect_all` 已 try 但本源也要自我兜底)。
- 用 `httpx`(项目已依赖),不引新库。token 文件读写只用标准库。

### 字段归一化 `normalize(task, list)`
输出**和 Apple 提醒完全相同的字段名**,这样下游零改动:
| 输出字段 | 来源 | 说明 |
|---|---|---|
| `title` | `task.title` | |
| `completed` | `task.status == "completed"` | |
| `dueDate` | `task.dueDateTime.dateTime` | 可空;保持 ISO,下游只取前 10 位 |
| `priority` | `task.importance == "high"` → 高优先级 | 对齐 Apple 的 priority 语义 |
| `list` | `list.displayName` | |
| `source` | 常量 `"mstodo"` | 内部留存(调试/未来用),**面板不展示、不据此区分**(见 §9 决策) |
| `id` | `task.id` | 内部留存(未来增量同步用),渲染不展示;**本期不做去重** |
| `list_id` | `list.id` | 同上 |

## 9. 合并策略与数据契约(已定稿 2026-06-07)
合并方式拍板如下,实现照此即可,**不要自行加复杂度**:

1. **不区分来源**:面板上苹果提醒和兔兔待办**混在一起显示**,不加 ●/○ 等来源标记。`source` 字段内部留着备用,但渲染层不读、不展示。理由:看板讲究简洁,用户只关心"要做啥"。
2. **不去重**:两源**直接拼接**,即使偶有重复也不做去重。理由:两个独立系统标题未必一致,按标题强去重容易误杀;真有人反馈再说。
3. **列表粒度先粗**:同步**全部真实列表**;`Flagged Emails` 由 `include_flagged_emails` 开关控制(默认关)。不做"逐列表勾选"的细粒度。
4. **只显示未完成**:沿用现有分类逻辑(已过期/今天/将到期),`completed` 的任务天然不进面板,无需特殊处理。

实现上的体现:
- 改动**仅一行**:
  ```python
  reminders = (cache.get("reminders") or []) + (cache.get("reminders_mstodo") or [])
  ```
  其余分类逻辑(逾期/今天/将到期/total)完全不动。
- **数据契约 `reminders.*` 字段不变**,风格作者无感知,`docs/data-contract.md` 无需改。

## 10. 测试(`tests/test_mstodo.py`,先写后实现)
mock 掉 httpx,不打真网络:
1. `normalize` 字段映射正确(completed / dueDate 空 / importance=high / source 标记)。
2. 分页:`graph_get_all` 跟随两页 `@odata.nextLink` 能把两页任务都取回。
3. `flaggedEmails` 列表在开关关闭时被跳过、打开时被包含。
4. 降级:token 文件缺失 / refresh 失败 / API 非 2xx → `collect` 返回 `None`,不抛异常。
5. access token 缓存:未过期不触发刷新,过期触发刷新且轮换保存新 refresh_token。
6. 合并:build_context 中 Apple + MS 两源同时存在时正确拼接、分类、计数。
> 运行:`python3 -m pytest tests/test_mstodo.py -q`

## 11. 装配清单(改了哪些文件)
- [ ] **(维护者前置)** 按 §6b 注册 Azure 应用,把 `client_id` 填进 schema 默认值(替换 `<PROJECT_AZURE_CLIENT_ID>`)
- [ ] `server/config/schema.py` —— 加 mstodo Section + home 启用条件
- [ ] `server/sources/mstodo.py` —— 新增采集器(含 token 刷新/轮换/分页/归一化/降级)
- [ ] `server/app.py` —— `SOURCES` 元组加入 `mstodo`;加 login start/status/logout 三个端点
- [ ] `server/render/build_context.py` —— 合并两源(一行)
- [ ] `web/setup.html` —— mstodo 状态化登录区块
- [ ] `tests/test_mstodo.py` —— 新增测试
- [ ] `docs/data-contract.md` —— 仅当做了 §9 的 source 标记才需更新
- [ ] `docs/install.md` —— 加一节「连接 Microsoft To Do」(网页点按钮即可,无需命令行)

## 12. 验收标准
1. 不启用 mstodo 时:行为与现状完全一致,无任何报错。
2. 设置网页点按钮 → 授权 → 显示「已连接 + 账号 + 列表数」。
3. 看板 home 页能看到 MS To Do 的**未完成**任务,与 Apple 提醒混排、按时间正确分类。
4. 拔网络 / token 失效:MS 任务消失,Apple 提醒与其他页正常,无空屏无异常。
5. 仓库任何文件都搜不到 token 明文;token 文件不被 git 跟踪。
6. `python3 -m pytest tests/ -q` 全绿。

## 13. POC 已验证的事实(实现时可直接信赖)
- **能读**:个人 outlook.com 账号,设备码流程 + Microsoft Graph 成功读出列表与任务,并拿到 refresh token。
- **设备码流程可行**:POC 当时借了微软公开客户端 ID `14d82eec-204b-4c2f-b7e8-296a70dab67e`(Graph CLI 的)验证通过。**但开源产品改用项目自有应用**(见 §6b 决策),代码逻辑完全一致、只换 `client_id` 与 authority(`/common`),公开客户端 ID 仅作"流程能跑通"的佐证,不作为最终内置值。
- **`/me/todo/lists` 只返回真实列表**(如 `任务`、用户自建列表、`Flagged Emails`),**智能视图(我的一天/重要/计划内/已分配给我)不会出现**在这里,因此不会重复;它们应由本地字段重算,不要尝试同步。
- **`Flagged Emails`** 列表的 `wellknownListName` 为 `flaggedEmails`,据此识别并按开关过滤。
- **refresh token 会轮换**:刷新时若返回新 token 必须覆盖保存。
- 关键端点(`{authority}` 生产用 `https://login.microsoftonline.com/common`,见 §6b):
  - 设备码:`POST {authority}/oauth2/v2.0/devicecode`
  - 取/刷新 token:`POST {authority}/oauth2/v2.0/token`
  - 列表:`GET https://graph.microsoft.com/v1.0/me/todo/lists`
  - 任务:`GET https://graph.microsoft.com/v1.0/me/todo/lists/{listId}/tasks`(分页 `@odata.nextLink`)
  - 账号名(可选,登录后显示用):`GET https://graph.microsoft.com/v1.0/me`(取 `userPrincipalName`/`displayName`)
- **POC 参考实现**(设备码 + 读取的最小可跑版,只用标准库):
  `/mnt/work/kindle/work/mstodo_poc.py`(老仓库 work 目录,**仅作参考,不要直接搬进开源仓库**——开源版要用 httpx、做进网页、加分页与轮换)。
