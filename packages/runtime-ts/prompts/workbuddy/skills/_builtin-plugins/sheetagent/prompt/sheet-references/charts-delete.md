---
name: charts-delete
description: >
  Delete a chart with sheet.removeChart(chartId) — pass the drawingId directly, or look it up via
  getCharts(). No type block or styling rules needed (does not load charts-visual). Read before
  removeChart. Triggers on: 删除图表 / 删图 / 移除图表 / 去掉图表; "remove / delete a chart",
  "get rid of the chart".
---

# Sheet Charts — Deleting a Chart

> **Read this file before `sheet.removeChart(...)`.** Deleting a chart needs no type block and no
> styling rules — it does **not** load charts-visual. The `removeChart` / `getCharts` /
> `EmbeddedChart` method signatures live in **sheet-api-reference**. Creating or modifying a chart
> lives in **charts-create** / **charts-edit**.

## Pass the `chartId` directly

> **Delete a chart by calling `sheet.removeChart(chartId)`** with the `drawingId` string you used at
> `newChart` time. `removeChart` accepts **only** a chart id string — it does **not** take an
> `EmbeddedChart` object. There is no need to call `getCharts()` first if you already know the id.
>
> **NEVER call `newChart(existingDrawingId, ...)` to "get a reference" to a chart you intend to delete.**
> `drawingId` must be **unique** at creation; reusing an existing id with `newChart` conflicts in the
> backend (the engine already holds that id for the live chart) — the script will fail at `addChart`
> and never reach `removeChart`. `newChart` is for **creating** a chart only.

```javascript
const sheet = SpreadsheetApp.getActiveSheet();

// Delete by chartId (the drawingId you passed to newChart):
sheet.removeChart('chart_001');
```

> If you don't know the id, look it up first via `getCharts()` (match by `getDrawingId()` /
> `getTitle()` / index) and then pass the matched chart's `getDrawingId()`:
>
> ```javascript
> const charts = sheet.getCharts();
> const target = charts.find(c => c.getTitle() === 'Monthly Sales');
> if (target) sheet.removeChart(target.getDrawingId());
> // If charts is empty / no match, there is nothing to delete — do NOT fabricate a chart to remove.
> ```
>
> To delete **every** chart on the sheet:
> `sheet.getCharts().forEach(c => sheet.removeChart(c.getDrawingId()));`.
