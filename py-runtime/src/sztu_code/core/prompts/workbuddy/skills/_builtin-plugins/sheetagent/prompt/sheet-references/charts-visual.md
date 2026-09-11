---
name: charts-visual
description: >
  The chart visual contract: ChartType enum values, ChartOptions / ChartTextStyle type shapes,
  plus the styling-decision rules — title / legend / font-size hierarchy, axis scale derivation,
  data-label density, series colors. Read whenever a chart task needs a chart-type value, the
  options type shape, or a styling / axis-scale / data-label decision. Triggers on: 图表样式 /
  配色 / 系列颜色 / 字号 / 坐标轴刻度 / scale / 数据标签 / 图例; "chart styling / colors /
  axis scale / data labels / legend / fonts". Loaded with charts-create for every chart creation,
  and with charts-edit only when an edit changes a visual attribute (not for a pure setDataRange rebind).
---

# Sheet Charts — Visual Contract (Chart Types, Options Shape & Styling Rules)

> **This reference is the single source of truth for the chart *visual* layer:** the `ChartType`
> enum values, the `ChartOptions` / `ChartTextStyle` type shapes, and every styling decision —
> title / legend / font-size hierarchy, axis scale derivation, data-label density, series colors.
> Read it whenever a chart task needs a chart-type value, the options type shape, or a
> styling / axis-scale / data-label decision. **charts-create** always loads this file together with
> itself (creation must apply full styling in the same `newChart` call — see system prompt rule 12),
> and **charts-edit** loads it whenever an edit touches a visual attribute (not for a pure
> `setDataRange` rebind). The chart *method* signatures (`Sheet.newChart` / `EmbeddedChart`) live in
> **sheet-api-reference**; how to build / place / delete a chart lives in **charts-create** /
> **charts-edit** / **charts-delete**.

## Chart type contract — `ChartType` enum values

These are the accepted `chartType` string values for `sheet.newChart(...)`. Pass the string directly
(e.g. `'LINE'`). The combo entries carry usage notes — full combo patterns live in **charts-create**.

```typescript
ChartType: {
  AREA: "AREA";
  LINE: "LINE";
  RADAR: "RADAR";
  SCATTER: "SCATTER";
  PIE: "PIE";
  DOUGHNUT: "DOUGHNUT";
  BAR: "BAR";
  COLUMN: "COLUMN";
  PIE_OF_PIE: "PIE_OF_PIE";
  BUBBLE: "BUBBLE";
  /** Custom combo chart — MUST be used together with ChartOptions.series[i].type / .axis.
   *  If every series omits `type`, the backend falls back to its built-in default and
   *  renders **all series as clustered columns** (a semantically neutral fallback;
   *  it does NOT auto-add a line or area, which is rarely what the user wants).
   *  Always set series[i].type / .axis explicitly, OR switch to one of the three
   *  Excel presets below. See **charts-create** (Combo Charts) for the recommended patterns. */
  CUSTOM_COMBO: "CUSTOM_COMBO";
  /** Excel preset combo — clustered column + line, sharing one y-axis. The last series defaults to the line. */
  CLUSTERED_COLUMN_AND_LINE_COMBO: "CLUSTERED_COLUMN_AND_LINE_COMBO";
  /** Excel preset combo — clustered column + line, with the line bound to the SECONDARY axis.
   *  **Strongly recommended for "revenue + growth-rate" style dual-axis scenarios** where the
   *  two metrics have very different magnitudes. */
  CLUSTERED_COLUMN_AND_LINE_ON_SECONDARY_AXIS_COMBO: "CLUSTERED_COLUMN_AND_LINE_ON_SECONDARY_AXIS_COMBO";
  /** Excel preset combo — stacked area + clustered column. The first series defaults to the area. */
  STACKED_AREA_AND_CLUSTERED_COLUMN_COMBO: "STACKED_AREA_AND_CLUSTERED_COLUMN_COMBO";
  TREEMAP: "TREEMAP";
  STACKED_BAR: "STACKED_BAR";
  PERCENT_STACKED_BAR: "PERCENT_STACKED_BAR";
  STACKED_COLUMN: "STACKED_COLUMN";
  PERCENT_STACKED_COLUMN: "PERCENT_STACKED_COLUMN";
  STACKED_LINE: "STACKED_LINE";
  PERCENT_STACKED_LINE: "PERCENT_STACKED_LINE";
  MARKER_LINE: "MARKER_LINE";
  STACKED_MARKER_LINE: "STACKED_MARKER_LINE";
  PERCENT_STACKED_MARKER_LINE: "PERCENT_STACKED_MARKER_LINE";
  STACKED_AREA: "STACKED_AREA";
  PERCENT_STACKED_AREA: "PERCENT_STACKED_AREA";
  BAR_OF_PIE: "BAR_OF_PIE";
  SMOOTH_LINE_AND_MARKER_SCATTER: "SMOOTH_LINE_AND_MARKER_SCATTER";
  SMOOTH_LINE_SCATTER: "SMOOTH_LINE_SCATTER";
  STRAIGHT_LINE_AND_MARKER_SCATTER: "STRAIGHT_LINE_AND_MARKER_SCATTER";
  STRAIGHT_LINE_SCATTER: "STRAIGHT_LINE_SCATTER";
  MARKER_RADAR: "MARKER_RADAR";
  FILLED_RADAR: "FILLED_RADAR";
  FUNNEL: "FUNNEL";
  HISTOGRAM: "HISTOGRAM";
  WATERFALL: "WATERFALL";
};
```

## Options type shapes — `ChartTextStyle` & `ChartOptions`

```typescript
interface ChartTextStyle {
  fontFamily?: string;
  fontSize?: number;
  color?: string;
  bold?: boolean;
  italic?: boolean;
}

interface ChartOptions {
  // Note: there is NO chart-level `textStyle` here. Backend silently
  // ignores `textStyle` at the top of `options`; set `textStyle` on each
  // visible sub-block instead (see the Styling section below — recommended sizes:
  // title 16/bold, axis title 12/bold, legend 12, tick label 11,
  // data label 10–11).
  title?: {
    text?: string;
    visible?: boolean;
    overlay?: boolean;
    textStyle?: ChartTextStyle;
  };
  /** Note: there is intentionally NO `type` field here. The x-axis type
   *  (CATEGORY / VALUE / DATE) is inferred from the source column's data type
   *  at chart creation and is **immutable** afterwards — the backend rejects
   *  any attempt to set/change it with `xAxis.type switching ... is not
   *  supported` and fails the whole run_command. To change the axis type,
   *  fix the source column (its numberFormat / value) and re-create the
   *  chart via newChart(...). See the Axes section below. */
  xAxis?: {
    visible?: boolean;
    title?: {
      text?: string;
      visible?: boolean;
      textStyle?: ChartTextStyle;
    };
    labelPosition?: "HIGH" | "LOW" | "NEXT_TO" | "NONE";
    numberFormat?: string;
    majorTickMark?: "CROSS" | "INSIDE" | "OUTSIDE" | "NONE";
    minorTickMark?: "CROSS" | "INSIDE" | "OUTSIDE" | "NONE";
    gridlines?: boolean;
    minorGridlines?: boolean;
    textStyle?: ChartTextStyle;
  };
  yAxis?: {
    visible?: boolean;
    title?: {
      text?: string;
      visible?: boolean;
      textStyle?: ChartTextStyle;
    };
    scale?: {
      min?: number;
      max?: number;
      orientation?: "MIN_MAX" | "MAX_MIN";
    };
    majorUnit?: number;
    minorUnit?: number;
    labelPosition?: "HIGH" | "LOW" | "NEXT_TO" | "NONE";
    numberFormat?: string;
    majorTickMark?: "CROSS" | "INSIDE" | "OUTSIDE" | "NONE";
    minorTickMark?: "CROSS" | "INSIDE" | "OUTSIDE" | "NONE";
    gridlines?: boolean;
    minorGridlines?: boolean;
    textStyle?: ChartTextStyle;
  };
  /** Secondary y-axis (right side). Only takes effect in combo charts that have
   *  at least one SECONDARY series; ignored otherwise. Field shape is identical
   *  to yAxis — the backend matches them by OOXML val_ax.ax_pos == 'r'.
   *  Compatibility: when `secondaryYAxis` is omitted, the backend falls back and
   *  applies `yAxis` to the secondary axis too (legacy behavior). To keep primary
   *  and secondary `scale.min/max` independent, you MUST provide both explicitly.
   *  Typical example (column revenue + crosses-zero growth-rate line; each axis
   *  computed from a data-scan (see the Axes section below) on its own source columns):
   *    yAxis:          { scale: { min: 0,     max: 500  }, numberFormat: '#,##0', gridlines: true  },
   *    secondaryYAxis: { scale: { min: -0.20, max: 0.40 }, numberFormat: '0.0%',  gridlines: false } */
  secondaryYAxis?: {
    visible?: boolean;
    title?: {
      text?: string;
      visible?: boolean;
      textStyle?: ChartTextStyle;
    };
    scale?: {
      min?: number;
      max?: number;
      orientation?: "MIN_MAX" | "MAX_MIN";
    };
    majorUnit?: number;
    minorUnit?: number;
    labelPosition?: "HIGH" | "LOW" | "NEXT_TO" | "NONE";
    numberFormat?: string;
    majorTickMark?: "CROSS" | "INSIDE" | "OUTSIDE" | "NONE";
    minorTickMark?: "CROSS" | "INSIDE" | "OUTSIDE" | "NONE";
    gridlines?: boolean;
    minorGridlines?: boolean;
    textStyle?: ChartTextStyle;
  };
  legend?: {
    visible?: boolean;
    position?: "TOP" | "BOTTOM" | "LEFT" | "RIGHT" | "TOP_RIGHT";
    overlay?: boolean;
    textStyle?: ChartTextStyle;
  };
  series?: Array<{
    color?: string;
    dataLabel?: {
      visible?: boolean;
      showValue?: boolean;
      showPercentage?: boolean;
      showCategoryName?: boolean;
      showSeriesName?: boolean;
      position?:
        | "BEST_FIT"
        | "CENTER"
        | "INSIDE_BASE"
        | "INSIDE_END"
        | "OUTSIDE_END"
        | "ABOVE"
        | "BELOW"
        | "LEFT"
        | "RIGHT";
      numberFormat?: string;
      textStyle?: ChartTextStyle;
    };
    /** Per-series chart type (combo charts only). When any series[i].type
     *  disagrees with the top-level chartType, the shim auto-rewrites the
     *  whole chart_type to customCombo on the wire. OOXML only allows mixing
     *  COLUMN / STACKED_COLUMN / LINE / MARKER_LINE / AREA / STACKED_AREA;
     *  other values (PIE / SCATTER / BUBBLE / RADAR / ...) are silently
     *  ignored by the backend. See **charts-create** (Combo Charts). */
    type?:
      | "COLUMN" | "STACKED_COLUMN"
      | "LINE" | "MARKER_LINE"
      | "AREA" | "STACKED_AREA";
    /** Numeric axis this series is bound to. SECONDARY = right-side secondary
     *  axis (required for "revenue + growth-rate" style dual-axis charts);
     *  defaults to PRIMARY. Only takes effect in combo charts (a chart with
     *  at least one series whose type differs from the top-level chartType,
     *  or where the top-level type is CUSTOM_COMBO / a secondary-axis preset). */
    axis?: "PRIMARY" | "SECONDARY";
  }>;
}
```

## Chart Styling Recommendations

> Default-styled charts often look bare (no title, no legend). The recommendations below
> should be **passed in the `options` argument of `newChart(...)` in a single call** — do NOT do
> "create a default chart first, then call `chart.setOptions({...})` to style it" as two steps:
> that adds an extra write, shows the user an unstyled intermediate chart, and risks leaving an
> "ugly half-finished chart" if the flow is interrupted. Reserve `setOptions` for **modifying an existing chart** (see **charts-edit**).
> Even when the user did not explicitly specify title / legend details, fill in the reasonable defaults below — do not skip them.

> **Series colors** — do NOT set `series[i].color` by default. Let the platform apply its built-in palette so charts stay visually consistent with the workbook's theme. Only set colors when the user explicitly asks for a specific palette / brand color / per-series color mapping. If you do set them, use `#RRGGBB` (not CSS names like `'red'` / `'blue'`).

**Font defaults (per sub-block, REQUIRED)** — there is **no chart-level default `textStyle`**; the backend ignores any `textStyle` at the top level of `options`. Every sub-block that has visible text MUST carry its own `textStyle.fontSize`, otherwise that text falls back to the platform's bare default (which doesn't match the rest of the workbook).

- Sub-blocks that need an explicit `textStyle`: `title.textStyle` / `legend.textStyle` / `xAxis.textStyle` / `yAxis.textStyle` / `yAxis.title.textStyle` (and `secondaryYAxis.title.textStyle` when the secondary y-axis title is enabled) / `series[i].dataLabel.textStyle`. **Note**: at chart-creation time (`newChart`) the x-axis title is never configured (see Axes below), so do NOT emit `xAxis.title.textStyle` then — **except for `SCATTER`, where both the x-axis title and its `textStyle` ARE required at creation (see charts-create — Scatter Charts).** If the user later explicitly asks to add an x-axis title via `setOptions`, send a minimal patch `{ xAxis: { title: { text: ..., visible: true, textStyle: { bold: true, fontSize: 12 } } } }` — see **charts-edit**.
- Recommended sizes (establish the hierarchy: title > axis title > body > tick / data label):
  - **Title**: `{ bold: true, fontSize: 16 }`
  - **Axis title** (`yAxis.title.textStyle` / `secondaryYAxis.title.textStyle` — and `xAxis.title.textStyle` if the user explicitly asks for an x-axis title later via `setOptions`): `{ bold: true, fontSize: 12 }`
  - **Legend**: `{ fontSize: 12 }`
  - **Tick labels** (`xAxis.textStyle` / `yAxis.textStyle`): `{ fontSize: 11 }`
  - **Data label** (`series[i].dataLabel.textStyle`): `{ fontSize: 11 }` (range 10–11)
- **Color** stays at the platform default (black); do not set `textStyle.color` unless the user asks.

**Title** — one sentence telling the user "what they're looking at": include the time / object / scope.

- The text should be informative (e.g. `'2025 Q1 Channel Revenue Share'`); avoid placeholders like `'Chart1'` / `'Chart'` / `'Visualization'`.
- `textStyle: { bold: true, fontSize: 16 }`; default color is black (no need to set `textStyle.color` explicitly). The bold + larger size makes the title stand out above body text.
- `visible` defaults to `true`. **Always emit `overlay: false` explicitly** — OOXML's default is `true`, which makes the title cover the plot area and clash with the data when the workbook is opened in native Excel. The Shim layer will auto-inject `overlay: false` when omitted, but writing it explicitly keeps the intent visible in the script.

```javascript
{
  title: {
    text: '2025 Monthly Revenue by Product Line',
    visible: true,
    overlay: false,                                  // required — OOXML default is true
    textStyle: { bold: true, fontSize: 16 },
  },
}
```

**Legend** — required for multi-series, optional for single-series.

- Multi-series (≥2): `visible: true` is required, otherwise the user cannot tell which color maps to which series.
- Single-series: the legend is just dead space; set `visible: false` and let the title carry the meaning.
- **Default `position`: `'BOTTOM'` for ALL chart types** (column / bar / line / area / scatter / pie / doughnut / radar). Bottom keeps a consistent layout across the workbook and leaves the most horizontal space for the plot area. Only switch to `'RIGHT'` when the legend has many entries (typically a pie / doughnut with 8+ categories) and `'BOTTOM'` would wrap into 3+ rows, or when the user explicitly asks for a side legend.
- `textStyle: { fontSize: 12 }` (body size) — always set explicitly; there is no chart-level fallback, omitting it makes the legend render at the platform's bare default.
- `overlay` defaults to `false`; do **not** set `true` unless the user explicitly asks for a tight overlay layout — `true` puts the legend on top of the data and hides values.

```javascript
{
  legend: {
    visible: true,
    position: 'BOTTOM',          // default for all chart types
    textStyle: { fontSize: 12 },
  },
}
```

**Axes** (`xAxis` / `yAxis`) — directly affect read-accuracy of the chart.

- **Axis titles**:
  - **`xAxis.title` — do NOT configure on chart creation (`newChart`).** The x-axis carries categorical labels (month names, product names, region codes, dates, IDs, …) that already speak for themselves; auto-adding an `xAxis.title` block at creation time just duplicates content and crowds the plot area. So when calling `newChart(...)`, omit the `xAxis.title` block entirely (no `text`, no `visible`, no `textStyle`).
  - **Exception — `SCATTER` charts.** A scatter's x-axis is a numeric VALUE axis with no self-describing labels, so its x-axis title is required and MUST be set at creation (with `textStyle: { bold: true, fontSize: 12 }`, plus **`overlay: false`** — see the axis-title overlay rule below). This is the one chart type where you emit `xAxis.title` in the `newChart` call — see **charts-create** (Scatter Charts).
  - **Exception — explicit user request on an existing chart.** If the user *explicitly* asks you to add / change / remove an x-axis title on a chart that already exists (e.g. *"add an x-axis title 'Month'"*), send a minimal `setOptions` patch with just the `xAxis.title` block (`text`, `visible: true`, `overlay: false`, `textStyle: { bold: true, fontSize: 12 }`) — see **charts-edit**. Do **not** invent an `xAxis.title` on your own initiative — only do it when the user explicitly asks.
  - **`yAxis.title.text` — required** when the column header is an abbreviation or units are not explicit (e.g. `"Revenue ($)"`, `"GMV ($M)"`, `"DAU"`); may be omitted when the column header is already self-explanatory. Same rule applies to `secondaryYAxis.title.text` in combo charts.
  - **Axis-title `overlay: false` is required on every axis-title block you set** (`xAxis.title.overlay` / `yAxis.title.overlay` / `secondaryYAxis.title.overlay`). OOXML's default is `true`, which makes native Excel push the axis title on top of the plot area and overlap the tick labels. The Shim layer will auto-inject `false` when the block itself is present but `overlay` is omitted, but write it explicitly to keep the intent visible.
- **`numberFormat`**: almost always set on the y-axis — percent `'0.00%'` / currency `'$#,##0'` / thousands `'#,##0'`. Without it, long numbers like `1234567` will squeeze the x-axis.
- **`scale.min` / `scale.max` — MUST be derived from the actual data range** (never leave empty, never hard-code a guess). Workflow runs **before** `newChart(...)`:
  1. **Scan the source column(s)** the y-axis is bound to. Small/medium data: read via `get_cell_ranges` and compute `actualMin` / `actualMax` in the model. Large data (>2000 cells): compute inside `run_command` with `Math.min(...col)` / `Math.max(...col)` and return the pair.
  2. **`scale.max`** = `actualMax` rounded UP by ~5% and snapped to a clean step (1 / 5 / 10 / 50 / 100 / 0.05 / 0.5 / … pick by magnitude). Example: `actualMax = 478` → `max: 500`; `actualMax = 0.34` → `max: 0.40`.
  3. **`scale.min`** depends on chart type + sign of the data:
     - **Column / bar / stacked column / stacked bar / area / stacked area** → **hard-code `0`** (basic data-viz rule; non-zero baselines on a bar chart visually exaggerate differences and mislead the reader). Skip the data-driven `min` here.
     - **Line / scatter / marker line / radar, data all non-negative**:
       - If `actualMin ≤ actualMax * 0.5` (data spans from near-zero up to max) → `min: 0`.
       - Otherwise (data clustered in a narrow upper band) → `actualMin` rounded DOWN by ~5%, snapped to a clean step. Example: `actualMin = 322`, `actualMax = 478` → `min: 300, max: 500`.
     - **Data crosses zero** (some negatives, some positives) → `actualMin` rounded DOWN by ~5% (more negative), snapped to a clean step. Example: `actualMin = -0.18, actualMax = 0.34` → `min: -0.20, max: 0.40`.
  4. **Forbidden defaults**: ❌ omitting `scale` and relying on the platform's auto-fit (tick spacing becomes unstable and inconsistent across charts); ❌ hard-coding guessed values like `max: 100` / `max: 1000` / `max: 10000` without scanning data (real data above the cap gets clipped; real data far below makes the chart look flat).
- **`gridlines`**: turn on for the **primary** y-axis (`yAxis.gridlines: true`) — helps eyeballing values horizontally; default off for the x-axis (column width already separates categories — extra vertical lines look noisy). **Default off for the secondary y-axis (`secondaryYAxis.gridlines: false`)** — two sets of horizontal gridlines from primary + secondary overlap and clash, leaving the plot area visually noisy. Always emit `secondaryYAxis.gridlines: false` explicitly when configuring a combo chart with a secondary axis; do not rely on the fallback.
- **`textStyle`**: tick labels at `{ fontSize: 11 }`; axis title at `{ fontSize: 12, bold: true }`. Always set tick-label `textStyle` explicitly — there is no chart-level fallback, omitting it makes the axis render at the platform's bare default. Axis-title `textStyle` is only emitted when that axis title itself is enabled — by default that means `yAxis.title` (and `secondaryYAxis.title` in combo charts); the x-axis title is normally off at creation time, and its `textStyle` only needs to be set if the user later explicitly asks to enable it via `setOptions`.
- **`xAxis.type` is NOT a configurable field** (no `'CATEGORY'` / `'VALUE'` / `'DATE'` switching). The backend rejects axis-type changes with `xAxis.type switching (CATEGORY / VALUE / DATE) is not supported` and the whole `run_command` fails. The x-axis type is **inferred from the source column's data type at chart creation** (text → CATEGORY, numbers → VALUE, dates → DATE), and is **immutable** after creation. To change it, you must rebuild the source data (e.g. convert a text column of date-looking strings into real dates via cell `numberFormat` + `value`), then re-create the chart with `newChart(...)`. Do NOT emit `xAxis.type` in either `newChart` options or `setOptions` patches.

```javascript
// Assume a column chart over revenue data; source data scan: actualMin=120, actualMax=478.
//   yAxis.scale.min: 0      (column chart → hard-coded 0)
//   yAxis.scale.max: 500    (ceil(478 * 1.05) snapped to nearest 50)
{
  // At creation time, do NOT emit `xAxis.title` (see Axis titles rule above).
  // Only add it later via setOptions if the user explicitly asks.
  xAxis: {
    gridlines: false,
    textStyle: { fontSize: 11 },
  },
  yAxis: {
    title: { text: 'Revenue ($)', visible: true, textStyle: { fontSize: 12, bold: true } },
    numberFormat: '#,##0',
    scale: { min: 0, max: 500 },
    gridlines: true,
    textStyle: { fontSize: 11 },
  },
}
```

**Data labels** (`series[i].dataLabel`) — write the value directly on the data point; decide which flags to enable based on density + chart type.

**MANDATORY preflight before emitting any `series[i].dataLabel` block** — count data rows first, then decide. Do not decide from chart size, aesthetics, font size, or label position.

```javascript
const pointsPerSeries = dataRangeRows - headerRows; // usually: dataRangeRows - 1
const isPieLike = chartType === 'PIE' || chartType === 'DOUGHNUT';
const enableDataLabels = isPieLike || pointsPerSeries <= 9;
```

If `enableDataLabels` is `false`, you MUST NOT emit `dataLabel.visible: true`. **To disable labels, omit the `dataLabel` block entirely — never emit `dataLabel: { visible: false }` in a `newChart` call** (that explicit form is only for `setOptions` on an existing chart). Drop `dataLabel` from the series entry, or omit the `series` block when it carries nothing else:

```javascript
series: [{ /* no dataLabel key → no labels */ }]   // or omit `series` entirely
```

For example, `sheet.getRange(1, 10, 12, 2)` used for a `BAR` chart has 1 header row + 11 data rows, so it is **11 points/series**. Because it is not pie-like, data labels MUST be disabled.

- **Whether to enable** — judged by **data points per series after excluding header rows**, not total points across the chart. Count first, then decide:
  - **Pie / doughnut — ALWAYS enable.** Regardless of the number of slices, pie and doughnut charts must always have `dataLabel.visible: true`. The density rule below does NOT apply to pie / doughnut.
  - **≤ 9 points/series** → enable (the user reads values at a glance, no need to consult the y-axis).
  - **≥ 10 points/series** → **MUST disable** (except pie / doughnut — see above). This is a hard stop for non-pie-like charts: do not emit `dataLabel.visible: true`, and do not try to rescue it by shrinking `fontSize`, changing `position`, or making the chart wider. To disable, **omit the `dataLabel` block** — never emit `dataLabel: { visible: false }` in a `newChart` call.
  - **Multi-series rule**: if **any** series in the chart has ≥ 10 points, disable data labels for **every** series — mixing labeled and unlabeled series in the same chart looks inconsistent. (This rule does not apply to pie / doughnut, which always keep labels enabled.)
- **Default: enable exactly ONE `show*` flag.** Stacking multiple flags (e.g. `showValue` + `showCategoryName`, or `showValue` + `showPercentage`) crowds the label and rarely improves readability. Pick one based on chart type:
  - Column / bar / line / area: only `showValue: true`, paired with `numberFormat` (the data label has its own format, independent of the y-axis `numberFormat`).
  - Pie / doughnut: only `showCategoryName: true`. Category names directly on each slice make the chart self-explanatory without consulting the legend.
- **The four `show*` flags are mutually exclusive — set exactly one to `true` and explicitly emit the other three as `false`.** Do not rely on omission. The four flags are `showValue`, `showPercentage`, `showCategoryName`, `showSeriesName`; pinning the unused three to `false` makes intent explicit across hosts and prevents the platform from picking up a different default. In particular, when switching a chart to pie/doughnut, set `showCategoryName: true` and explicitly set `showValue: false`, `showPercentage: false`, `showSeriesName: false`. Only flip `showPercentage` or `showValue` to `true` when the user explicitly asks for it.
- **`position`** — default is **outside the data point** so the label never overlaps the marker / bar / slice. Pick by chart type:
  - Column / bar: `'OUTSIDE_END'` (just above the bar).
  - Line / area: `'ABOVE'` (above the marker).
  - Pie / doughnut: `'INSIDE_END'` (inside the slice). Only fall back to `'OUTSIDE_END'` or `'BEST_FIT'` when there are many small slices and inside labels visibly collide or are unreadable.
- **`textStyle.fontSize`**: 10–11; larger sizes squeeze the plot area. Always set this explicitly — there is no chart-level fallback, omitting it makes the data label render at the platform's bare default.

```javascript
{
  series: [
    {
      // No `color` here — let the platform apply its default palette.
      dataLabel: {
        visible: true,                    // ≥ 10 points/series: omit the whole dataLabel block (never visible:false in newChart). Pie/doughnut: ALWAYS true.
        // Exactly one show* flag is true; the other three must be explicitly false.
        showValue: true,                  // pie/doughnut: set to false
        showPercentage: false,            // pie/doughnut: keep false (unless user asks)
        showCategoryName: false,          // pie/doughnut: set to true
        showSeriesName: false,
        position: 'OUTSIDE_END',          // line/area: 'ABOVE'; pie/doughnut: 'INSIDE_END'
        numberFormat: '#,##0',
        textStyle: { fontSize: 11 },
      },
    },
  ],
}
```

## Common visual pitfalls to avoid

- Emitting `xAxis.type` (`'CATEGORY'` / `'VALUE'` / `'DATE'`) in **either** `newChart` options or a `setOptions` patch → the backend rejects this with `xAxis.type switching (CATEGORY / VALUE / DATE) is not supported` and the entire `run_command` fails. The x-axis type is inferred from the source column's data type at creation time and is immutable. To change it, rebuild the source column (fix its `numberFormat` / `value`) and re-create the chart with `newChart(...)`.
- Emitting an `xAxis.title` block in a `newChart(...)` call when the user did **not** explicitly ask for one → at chart-creation time the x-axis title must be omitted (no `text`, no `visible`, no `textStyle`); see the Axes section above. Adding it later via `setOptions` is allowed **only** when the user explicitly asks for an x-axis title on an existing chart.
- Leaving `secondaryYAxis.gridlines` at its default (or copying `yAxis.gridlines: true` over) when the chart has a secondary y-axis → primary + secondary horizontal gridlines overlap and clash. Always emit `secondaryYAxis.gridlines: false` explicitly in combo charts with a SECONDARY axis.
- Setting `textStyle` at the **top level of `options`** → the backend ignores it (there is no chart-level default). Put `textStyle` on each visible sub-block instead: title 16/bold, y-axis title 12/bold, legend 12, tick label 11, data label 10–11.
- Omitting `textStyle` on `legend` / `xAxis` / `yAxis` (tick labels) / `series[i].dataLabel` and assuming a chart-level fallback → there is none, those sub-blocks will fall back to the platform's bare default. Always set each block's own `textStyle.fontSize` per the recommended sizes above.
- Leaving `dataLabel.visible: true` on a chart whose series has **10 or more data points** → labels overlap into an unreadable blob; you **must** turn them off by **omitting the `dataLabel` block**. Shrinking `fontSize` or changing `position` does not fix this, and never emit `dataLabel: { visible: false }` in a `newChart` call. **Exception: pie / doughnut charts always keep `dataLabel.visible: true`** regardless of slice count.
- Wrong: using `sheet.getRange(1, 10, 12, 2)` for a `BAR` ranking chart (1 header row + 11 data rows), then emitting `dataLabel.visible: true`. Right: this is **11 points/series**, so **omit the `dataLabel` block** (never emit `dataLabel: { visible: false }` in a `newChart` call).
- Stacking multiple `show*` flags on a data label by default (`showValue` + `showCategoryName`, `showValue` + `showPercentage`, etc.) → labels get crowded; pick exactly one unless the user explicitly asks for more. For pie / doughnut the default single flag is `showCategoryName: true` (not `showPercentage`).
- Omitting `scale` on `yAxis` / `secondaryYAxis` and relying on the platform's auto-fit → tick spacing becomes unstable and inconsistent across charts. Always derive `scale.min` / `scale.max` from the data via the workflow in the Axes section above (scan `actualMin` / `actualMax`, round, snap to a clean step).
- Hard-coding `scale.max` / `scale.min` without scanning the source data (e.g. always writing `max: 100` / `max: 1000` because it "looks round") → real data above the cap gets clipped, real data far below the cap makes the chart look flat. Scan first, then compute.
- Column / bar / area / stacked-* chart with `yAxis.scale.min` set to a non-zero value → visually exaggerates the difference; this category is the ONE exception to the "data-driven `min`" rule — always hard-code `0`.
- Setting `series[i].color` by default (rather than letting the platform palette apply) → only set colors when the user explicitly asks. If you do, use `#RRGGBB`, never CSS names like `'red'` / `'blue'`.
