# Data contract (for style authors)

> **A style = a different skin over the same set of data fields.** When you build a new style, the variables you can use in templates are exactly the ones listed here — names and types are frozen. With a stable contract, you can swap layouts and CSS freely without touching the data layer.
>
> The authoritative definition lives in `server/render/contract.py` (this doc is its human-readable summary; changes to the contract must be mirrored in both).
> When data is missing/unconfigured, every field has a degraded placeholder (numbers → `0`, text → `--`, lists → `[]`), so templates **never receive undefined** — use them freely.

## Page → data section

| Page key | Title | Data section used | Required data source (page hides if unconfigured) |
|---|---|---|---|
| `home` | Home | `home` + top-level | Weather, Reminders |
| `ai` | AI usage | `ai` | AI usage (ccusage) |
| `device` | Devices | `device` | Device monitoring |
| `ha` | Smart home | `ha` | Home Assistant + entities selected |
| `printer` | Printer | `printer` | Home Assistant |

## Top-level fields (available on all pages)

| Field | Type | Example | Notes |
|---|---|---|---|
| `lang` | str | `zh` / `en` | UI / dashboard language. Templates use `{% if lang == 'zh' %}…{% endif %}` to hide Chinese elements (English build) |
| `now` | str | `05/27 14:30` | date + time |
| `time_hm` | str | `14:30` | hour:minute |
| `clock` | str | `14:30:05` | hour:minute:second |
| `battery.level` | int\|`--` | `87` | Kindle battery |
| `battery.charging` | bool | | whether charging |
| `battery.has` | bool | | false when there's no battery data; templates should use this to decide whether to render the battery block |

> **i18n (Chinese/English)**: global switch `config.server.language` (zh|en, default zh).
> - **Data values are produced per-language** (display directly, don't re-translate): `home.weekday` (周X / Mon-Sun), `printer.state_text`/`speed`/`remaining_text`, `ai.*_reset` countdowns, reminder `.dt` labels, device section names `总容量` / `Total`.
> - **Chinese elements are blanked in the English build**: `home.lunar`/`ganzhi`/`term` = `""`; each calendar cell `l`=`""` and `holiday`=False (the Gregorian number stays).
> - **Static UI strings**: each style ships its own `styles/<style>/strings.json` (`{"zh":{...},"en":{...}}`); `render_page` injects them by `lang` as the template variable `t`, used as `{{ t.key }}` (a missing English key falls back to Chinese). The zh values are character-for-character identical to the original templates → the default Chinese stays pixel-identical.

## `home` — Home

| Field | Type | Example | Notes |
|---|---|---|---|
| `date_md` / `date_dot` | str | `05/27` / `05.27` | two date formats |
| `weekday` | str | `周三` | |
| `lunar` | str | `四月初一` | lunar date |
| `ganzhi` | str | `丙午马年` | sexagenary / zodiac |
| `term` | str | `今日芒种` / `夏至还有3天` / `` | solar term, may be empty |
| `year` / `month` | int | | |
| `weather.city` | str | `北京` | city name (GeoAPI reverse-lookup of location); empty if unconfigured / not found |
| `weather.temp` | str | `24` | current temperature |
| `weather.cond` | str | `多云` | conditions |
| `weather.feels` | str | `26` | feels-like |
| `weather.humidity` | str | `65` | humidity |
| `weather.wind` | str | `西北风3级` | |
| `weather.today_range` | str | `18–26°` | today's temp range |
| `weather.tmr_range` | str | `19–27°` | tomorrow's temp range |
| `weather.tmr_cond` | str | `晴` | tomorrow's conditions |
| `calendar` | list | | month grid: array of week rows; each cell is `None` (empty) or `{d, l, today, holiday, weekend}` |
| `reminders.overdue` | list | `[{title, dt}]` | overdue; dt e.g. `05.20` |
| `reminders.today` | list | `[{title, dt}]` | today |
| `reminders.upcoming` | list | `[{title, dt}]` | upcoming; dt e.g. `明天` / `+3天` / `05.30` |
| `reminders.total` | int | | total unfinished |

**Calendar cell** `{d:day, l:subtext (holiday/solar-term/lunar), today:bool, holiday:bool, weekend:bool}`

## `ai` — AI usage

| Field | Type | Example | Notes |
|---|---|---|---|
| `five_pct` / `five_reset` | int / str | `42` / `2小时后` | Claude 5h quota used% / reset countdown |
| `week_pct` / `week_reset` | int / str | | Claude weekly quota |
| `cx_five_pct` / `cx_five_reset` | int / str | | Codex 5h quota |
| `cx_week_pct` / `cx_week_reset` | int / str | | Codex weekly quota |
| `today_cost` | str | `$12.30` | today's total cost |
| `cc_cost` / `cc_tok` | str | `$8.10` / `1.2M` | Claude today's cost / tokens |
| `cx_cost` / `cx_tok` | str | `$4.20` / `0.6M` | Codex today's cost / tokens |
| `tok_7d` / `tok_30d` / `tok_all` | str | `8M` / `30M` / `120M` | cumulative tokens |
| `chart` | list | `[{day:"27", cc_h:60, cx_h:30, val:"1.2M"}]` | last-7-day bar chart; `cc_h`/`cx_h` are 0-100 height% |
| `custom_total` | str | `¥12.34` | today's official price × multiplier (`ai_usage.claude_rate`/`codex_rate`, one each). Empty (hidden) when both = 1.0 |
| `custom_name` | str | | provider name, currently always empty → templates fall back to "Custom" |
| `codex_on` | bool | `true` | from `ai_usage.codex_enabled`; `false` = templates hide the Codex quota block/legend (Claude-only) |

## `device` — Device monitoring

`device.machines` is a **dynamic machine list** (0–N machines, Windows/Linux/Mac), **iterated** in templates. Empty when there are no machines, and the page hides.
> Design new styles around an "iterable machine list" that adapts to 1 or many machines — **don't hardcode a count or machine name**. Each machine's `show` decides which metric bars appear.

Per-machine object fields:

| Field | Type | Notes |
|---|---|---|
| `name` | str | display name (customizable; push devices default to hostname) |
| `cpu` | int | CPU usage % |
| `mem` | int | memory usage % |
| `mem_used` / `mem_total` | str | memory |
| `net_rx` / `net_tx` | str | network receive/send rate |
| `disk_r` / `disk_w` | str | disk read/write rate |
| `vols` | list | `[{name, pct, used, total}]` per partition (already filtered by selection) |
| `show` | dict | `{cpu, mem, net, disk_io}` whether each metric bar shows (user selection; empty config = all True) |

Iteration pattern: `{% for m in device.machines %} ... {% if m.show.cpu %}CPU {{ m.cpu }}%{% endif %} ... {% endfor %}`

## `ha` — Smart home (entity card wall)

`ha.cards` is a list; the page hides when it's empty (config = pages). Each card's fields are frozen:

| Field | Type | Notes |
|---|---|---|
| `name` | str | display name (user override or HA friendly name) |
| `kind` | str | `toggle`/`lock`/`cover`/`binary`/`sensor`/`climate`/`media`/`presence`/`text` |
| `icon` | str | MDI icon name (`mdi:xxx`); empty = no icon |
| `on` | bool | active-state emphasis (on/present/locked/playing…); always `false` for sensor |
| `state_text` | str | primary text (toggle/lock/cover/binary/climate/media/presence/text) |
| `value` | str | primary value (sensor; empty for non-sensor) |
| `unit` | str | value unit (sensor; e.g. `°C` / `%` / `W`) |
| `sub` | str | secondary line (climate target temp, media title…), may be empty |

> Primary-display rule: `value` non-empty → big `value` + small `unit`; otherwise big `state_text`. A non-empty `sub` adds one more small line.
> Iteration pattern: `{% for c in ha.cards %} ... {% if c.value %}{{ c.value }}{{ c.unit }}{% else %}{{ c.state_text }}{% endif %} ... {% endfor %}`
> on/off is distinguished on e-ink by "outline vs heavy outline + solid dot", not by color.

## `printer` — Printer

When the whole thing is `None` the page degrades/hides. Otherwise:

| Field | Type | Notes |
|---|---|---|
| `online` / `printing` | bool | online / currently printing |
| `state_text` | str | `打印中` / `空闲` / `离线`... |
| `progress` | int | 0-100 |
| `task` | str | file name |
| `layer` / `total_layer` | str | current layer / total layers |
| `remaining_text` | str | `2小时15分` |
| `eta_clock` | str | estimated completion time `16:45` |
| `nozzle` / `nozzle_t` | str | nozzle temp / target |
| `bed` / `bed_t` | str | bed temp / target |
| `speed` | str | speed level |
| `weight` / `material` | str | filament weight / type |
| `cooling_fan` | str | fan speed |
| `name` | str | printer name |

> Currently fits a single 3D printer (Bambu Lab). P2 will abstract it into "any HA entity card" to reduce brand lock-in; the contract will then extend and this table will be updated.
