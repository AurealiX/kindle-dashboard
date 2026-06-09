# Style authoring brief (for style authors / AI)

> Your task: design a **new style skin** for Kindle Dashboard. Each style = a different look over the same data.
> Work from the repo root. **Read [`docs/data-contract.md`](data-contract.md) (the data contract) before you start.**

## Background (30 seconds)

A jailbroken Kindle 558 sits in landscape as an info dashboard. The server renders HTML with Jinja2 → headless Chromium screenshots it at **landscape 800×600** → the backend rotates it to portrait to write the e-ink screen (**you don't deal with rotation**).
All styles share the same **data contract** (field names/types frozen); you only do the look, never touch the data.

## Deliverable

One directory per style: `styles/<style-name>/`, containing 6 files:
```
home.html  ai.html  device.html  ha.html  printer.html  style.css
```
Use lowercase + underscores for the style name (e.g. `newspaper`, `terminal`, `minimal`).

## Hard rendering constraints (violations break layout — must follow)

1. **Fixed 800×600 landscape canvas**: `html,body{width:800px;height:600px;}`, no scrolling, no overflow.
2. **Pure grayscale e-ink**: only `#000`–`#fff` black/white/gray, **no color whatsoever**, no gradient filters. Convey hierarchy with halftone/diagonal patterns/solid blocks.
3. **Prevent overflow**: body uses `display:flex;flex-direction:column`; main body `flex:1;min-height:0;overflow:hidden`;
   footer `flex-shrink:0;margin-top:auto`. **Don't use `position:absolute`** (a historical overflow pitfall).
4. **Fonts**: for Chinese use `'Noto Sans CJK SC','PingFang SC','Microsoft YaHei',sans-serif` (cross-platform fallback);
   `monospace` is fine for a numeric/code feel. **No Chinese serif font** — get the newspaper/magazine "serif feel" from typography, not from serif.
5. Always add `font-variant-numeric:tabular-nums` to numbers (tabular figures, prevents jitter).
6. The first line of each html must be:
   `<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><style>` immediately followed by `{{ css|safe }}`,
   then this page's own CSS, then `</style></head><body>`. Put shared styles in `style.css`; per-page differences go in each html's `<style>`.
7. **Static screenshot**: no animation, JS, external resources, or web fonts. SVG (progress rings, etc.) is fine.

## Data contract (full fields in docs/data-contract.md; key points here)

Each page can use the top-level fields directly: `now`, `time_hm`, `clock`, `battery.{level,charging,has}`.
When data is missing, every field has a degraded placeholder (numbers → 0, text → `--`, lists → `[]`), so **templates never get undefined**.

Data section per page:
- **home**: `home.weather.*` (temp/conditions/feels-like/humidity/wind/today+tomorrow ranges), `home.calendar` (month grid week list), `home.reminders.{overdue,today,upcoming,total}`, lunar/ganzhi/solar-term
- **ai**: Claude/Codex `five_pct`/`week_pct` quotas, today's cost, `chart` (last-7-day bar chart), token stats
- **printer**: print state/progress/layers/remaining time/nozzle & bed temps etc.; the whole thing may be None, so guard with `{% if printer %}`
- **device**: see below (structure differs from the old dashboard — read carefully)
- **ha** (smart-home entity wall, new): `ha.cards` array, adaptive tiles; fields and approach in the `ha` section of `docs/data-contract.md`; **this page has its own build spec `docs/ha-page-styles-spec.md` (with sample-data script) — follow it for the ha page**. `style_a/ha.html` is the shipped baseline.

### ⚠️ The device page is a dynamic machine list (unlike the old version!)

`device.machines` is an **array**, 0 to N machines (Windows/Linux/Mac), to be **iterated** and rendered, adapting to any count:

```jinja
{% if device.machines %}
  {% for m in device.machines %}
    <!-- m.name display name; m.show controls which metric bars show; m.vols already filtered by selection -->
    <h3>{{ m.name }}</h3>
    {% if m.show.cpu %}CPU {{ m.cpu }}%{% endif %}
    {% if m.show.mem %}内存 {{ m.mem }}% {{ m.mem_used }}/{{ m.mem_total }}{% endif %}
    {% if m.show.net %}网络 ↓{{ m.net_rx }} ↑{{ m.net_tx }}{% endif %}
    {% if m.show.disk_io %}磁盘 读{{ m.disk_r }} 写{{ m.disk_w }}{% endif %}
    {% for v in m.vols %}{{ v.name }} {{ v.used }}/{{ v.total }} {{ v.pct }}%{% endfor %}
  {% endfor %}
{% else %}
  <div>暂无设备数据</div>
{% endif %}
```

Per-machine fields: `m.name`, `m.cpu` (int%), `m.mem` (int%), `m.mem_used`/`m.mem_total`, `m.net_rx`/`m.net_tx`, `m.disk_r`/`m.disk_w`, `m.vols[]` (`{name,pct,used,total}`), `m.show.{cpu,mem,net,disk_io}` (bool, user selection).
**The layout must gracefully handle 1, 2, or 4 machines** (use a flex-wrap grid, don't hardcode two columns).

## Unified footer (consistent across all 5 pages)

Each page's footer is fixed: update time · Kindle battery · page identifier. The battery must appear:
```jinja
{% if battery.charging %}充电 {% else %}电量 {% endif %}{{ battery.level }}%
```

## Landscape layout advice (800 wide — split into columns, don't copy a portrait stack)

- Header spans full width, footer spans full width, the middle body has 2–3 columns
- home: weather | month grid | reminders
- ai: left (quota bars + today's cost) | right (token stats + 7-day bar chart)
- device: machine card grid (adapts to count)
- ha: adaptive tile wall (`cols=ceil(sqrt(n))` capped at 4), on/off shown by solid vs outline (see the dedicated build spec)
- printer: left (progress ring + task + layers + remaining) | right (temps + details)

## Develop & preview

**Preview tool** (no server needed — one command renders all pages to PNG):
```bash
python3 scripts/preview_style.py <style-name>          # realistic mock data, landscape upright
python3 scripts/preview_style.py <style-name> --empty   # empty data, verifies graceful degradation
# outputs /tmp/preview_<style-name>_<page>.png — open to see the result
```
Iteration loop: edit template → run preview → look at PNG → edit again.

## Acceptance criteria

1. All 6 files present, correct style-name directory.
2. `preview_style.py <style-name>` and `--empty` **both run without errors**, all 5 pages output 800×600.
3. No overflow, no scroll, pure grayscale, no color.
4. The device page correctly iterates 1–N machines and respects the `m.show` selection.
5. A **distinct, strong visual direction** — don't copy style_a's look (reference its data bindings and overflow-prevention approach only).

## Reference

Learn the data bindings and overflow-prevention approach from any built-in style, but create your own visual direction.

## Built-in styles (7 total — **don't duplicate, use as reference**)

All verified (each covers the full home/ai/device/ha/printer pages, passing on both real and empty data):

- **style_a** — magazine / editorial (baseline reference)
- **terminal** — TUI command line, monospace + window borders + ASCII separators
- **bento** — bento grid, rounded soft-gray cards
- **blueprint** — engineering blueprint (grayscale), grid texture + double-line frames + annotations
- **minimal** — Swiss minimalism, big whitespace + oversized numbers + hairlines
- **newspaper** — newspaper, heavy masthead + multi-column hairlines + dense small type
- **gauge** — analog gauges, semicircular needle dials (circular language)

To add a style → pick a direction distinct from all of the above (e.g. dot-matrix, almanac, brutalist), build it under the constraints here, and verify with `python3 scripts/preview_style.py <name>`.
