---
name: charts-edit
description: >
  Modify an existing chart: the minimal-patch rule for setOptions (per-field deep-merge, no
  getOptions round-trip) and setDataRange rebinding. Read before any setOptions / setDataRange;
  also read charts-visual when the change touches a visual attribute. Triggers on: 改图 /
  修改图表 / 图表样式 / 改标题 / 改颜色 / 改配色 / 换坐标轴刻度 / 加数据标签 / 重新绑定数据;
  "restyle / recolor / retitle / rescale a chart", "change the axis / labels", "rebind the data".
---

# Sheet Charts — Modifying an Existing Chart

> **Read this file before any `setOptions` / `setDataRange` on an existing chart.** If the edit
> changes a **visual attribute** (restyle / recolor / retitle / rescale an axis / add-change data
> labels / legend / fonts), also Read **charts-visual** — it carries the type contract plus the
> styling / axis-scale / data-label rules you need to build a correct patch. If you are **only**
> rebinding data (`setDataRange`) or repositioning (`setPosition`), you do **not** need
> charts-visual — those method signatures live in **sheet-api-reference**. Creating a new chart
> lives in **charts-create**; deleting one lives in **charts-delete**.

## Send a Minimal Patch (HARD RULE)

`chart.setOptions(opts)` is a **per-field deep-merge** on the backend, NOT a whole-config replace. Only the keys you explicitly include in the payload are written to the underlying chart model; every field you omit (legend / axes / data labels / series styling / …) is preserved verbatim. Concretely:

- **Top-level objects** (`title` / `legend` / `xAxis` / `yAxis` / `secondaryYAxis` / `series` / …): merged by key — omitting one keeps it intact.
- **Nested objects** (e.g. `legend.textStyle`, `yAxis.scale`): also merged by field — sending `{ legend: { textStyle: { fontSize: 12 } } }` only writes `fontSize`, it does NOT clear `bold` / `color` / `fontFamily`.
- **`series` array**: merged **by index** on the backend — only the per-series fields the backend writes (`color` / `dataLabel`) are touched; other series-level fields are untouched. (Note: the local TS shim treats arrays as replace for its own cache, but the on-disk model still follows the per-index merge on the backend.)

**HARD RULE — send only the fields you want to change.** Do NOT do a `getOptions() → spread-merge full options → setOptions(merged)` round-trip. That pattern is unnecessary (the deep-merge is already on the backend) AND introduces **non-symmetric side effects**, because `getOptions()` only reflects a subset of the underlying OOXML model while `setOptions()` re-writes a few "hard-coded" fields whenever a sub-block is touched:

- Sending **any** `textStyle` block forces `body_pr.anchor_ctr = false` on the corresponding text body, regardless of its previous value.
- Sending `title.textStyle` / `xAxis.title.textStyle` / `yAxis.title.textStyle` (etc.) clears the run-level `r_pr` fields (`bold` / `italic` / `fontSize` / `fontFamily` / `color`) that were set through the chart UI — even if `getOptions()` did not surface them.
- A few other proto-only fields (numbering, sizing, hidden flags) are not reflected by `getOptions()` either, so "round-trip" is provably lossy.

**The correct pattern is the inverse of read-merge-write: send a flat patch with exactly the changed leaves.**

**Default for missing `fontSize`** — When you patch a sub-block that did NOT carry an explicit `textStyle.fontSize` before (legacy chart, or that sub-block was never styled), include `fontSize` in the same patch so the result is not left at the platform's bare default. Use the recommended hierarchy from charts-visual (title 16/bold, axis title 12/bold, legend 12, tick label 11, data label 10–11) when the recommended size for that sub-block is unambiguous; otherwise default to **`12`**. Do NOT pre-read `getOptions()` just to learn the existing `fontSize` — picking a sensible default per the hierarchy is sufficient and avoids the side effects above.

**Example — *"change this chart's title color to red, leave everything else alone":***

```javascript
const sheet = SpreadsheetApp.getActiveSheet();
const chart = sheet.getCharts()[0];

chart.setOptions({
  title: {
    textStyle: {
      color: '#FF0000',
      // No need to read the old fontSize; just set the recommended title size (or 12 if unclear).
      fontSize: 16,
      bold: true,
    },
  },
});
```

**Wrong vs right at a glance:**

```javascript
// ❌ Wrong — re-sending the full options blob from getOptions() forces
//   body_pr.anchor_ctr=false on every textStyle sub-block and clears run-level
//   r_pr fields on title / axis titles. Some unrelated styles WILL be lost.
const cur = chart.getOptions() ?? {};
chart.setOptions({
  ...cur,
  title: { ...(cur.title ?? {}), text: 'New Title' },
});

// ✅ Right — send only the leaf you want to change. The backend deep-merges
//   it on top of the existing config, no side effects on untouched sub-blocks.
chart.setOptions({
  title: { text: 'New Title' },
});
```

**More examples:**

```javascript
// Change legend font size only — nothing else gets re-written.
chart.setOptions({ legend: { textStyle: { fontSize: 12 } } });

// Tighten the y-axis upper bound only — min / numberFormat / gridlines / textStyle preserved.
chart.setOptions({ yAxis: { scale: { max: 500 } } });

// Repaint the first series — color of series[0] only, other series untouched.
chart.setOptions({ series: [{ color: '#1F77B4' }] });

// Add an x-axis title on user request — emit the full title block (it didn't exist before).
chart.setOptions({
  xAxis: {
    title: { text: 'Month', visible: true, textStyle: { bold: true, fontSize: 12 } },
  },
});
```

> Reminder: this rule applies to `setOptions` only. When **creating** a chart via `newChart(...)`, pass the full styling in the `options` argument in a single call — see system prompt rule 12 and **charts-create**. Do NOT do "create with defaults, then `setOptions` to style".

## Modifying a combo chart — minimal patch only

```javascript
// Tighten only the secondary axis upper bound; everything else preserved by the backend deep-merge.
const chart = sheet.getCharts()[0];
chart.setOptions({
  secondaryYAxis: {
    scale: { max: 0.6 },                            // only `max` is sent; min / numberFormat / textStyle / gridlines preserved
  },
});
```

## Rebinding data (`setDataRange`)

If the chart is bound to the wrong range (picked up an extra column, or missed one the user asked for), do NOT delete and re-create it, and do NOT copy the source data into a fresh "clean" block. Call `chart.setDataRange(sheet.getRange(...))` once with the corrected range — the styling (`options`) is preserved. For per-series shape changes that `setDataRange` cannot express (e.g. dropping a single series out of a multi-column block), fall back to `removeChart` + a new `newChart(...)` over the narrower range (see **charts-create** / **charts-delete**) — still do NOT precompute a helper table for this.

> A pure `setDataRange` rebind (or a `setPosition` reposition) changes no visual attribute, so you do **not** need to load charts-visual for it. Only the method signature is needed — it lives in **sheet-api-reference**.

## Common edit pitfalls

- Doing a `getOptions() → spread-merge full options → setOptions(merged)` round-trip on an existing chart → `setOptions` is already a per-field deep-merge on the backend, so the round-trip is **unnecessary** AND **lossy**: `getOptions()` only reflects a subset of the underlying chart proto, and re-sending any sub-block that carries `textStyle` triggers side effects (forces `body_pr.anchor_ctr=false`; clears run-level rich-text `r_pr` set through the chart UI). Always send a minimal patch with only the fields you want to change.
