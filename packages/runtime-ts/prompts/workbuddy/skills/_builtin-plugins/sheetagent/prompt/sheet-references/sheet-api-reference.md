---
name: sheet-api-reference
description: >
  Complete TypeScript API reference for all SpreadsheetApp, Spreadsheet, Sheet, Range, PivotTable,
  EmbeddedChart, Filter, Utility, and related interfaces available in SheetAgent scripts.
  Read before any `run_command` script that uses APIs you are unsure about, or when you need to
  verify exact method signatures, parameter types, or return shapes. You may ONLY use APIs listed
  here (or in another reference file you have read). Do NOT guess API names from memory.
  Covers: SpreadsheetApp globals / Spreadsheet / Sheet / Range /
  EmbeddedChart / Filter / Utility / BorderSide / TableInfo / ConditionalFormat
  interfaces / ProtectRange interfaces (CLOUD_AGENT only). The PivotTable class and
  PivotTableDetailData typings live in the sheet-pivot-tables reference; this file keeps only
  the Sheet/Range pivot method signatures and PivotTableObjectInfoData. The chart-type contract —
  the ChartType enum values, ChartOptions and ChartTextStyle type shapes — lives in the
  charts-visual reference; this file keeps the Sheet chart method signatures (newChart /
  insertChart / removeChart / getCharts), the EmbeddedChart class, and ChartObjectInfoData.
---

# Sheet API Reference — Complete TypeScript Declarations

> **You may ONLY use the APIs listed below.** Do not guess API names from memory. If an API is not listed here, treat it as unavailable. Calling an undocumented API throws a `TypeError` that aborts the whole script — the message names a working alternative when one exists, so read it before retrying. If the required API does not exist, use JavaScript logic with existing APIs to achieve the goal (e.g., sort data in a JS array then write back with `setValues`). Do NOT guess or invent API methods.

## 1. API Reference

```typescript
declare global {
  var SpreadsheetApp: {
    getActiveSpreadsheet(): Spreadsheet;
    getActiveSheet(): Sheet;
    getActiveRange(): Range;

    Dimension: {
      ROWS: "ROWS";
      COLUMNS: "COLUMNS";
    };
    BorderStyle: {
      DOTTED: "DOTTED";
      DASHED: "DASHED";
      SOLID: "SOLID";
      SOLID_MEDIUM: "SOLID_MEDIUM";
      SOLID_THICK: "SOLID_THICK";
      DOUBLE: "DOUBLE";
    };
    // ChartType — accepted `chartType` string values for sheet.newChart(...).
    // Values + ChartOptions/ChartTextStyle shapes and styling rules live in charts-visual.
    ChartType: { /* values: see charts-visual */ };
  };

  class Spreadsheet {
    getActiveSheet(): Sheet;
    getActiveRange(): Range;
    getSheetById(sheetId: string): Sheet;
    getSheetByName(name: string): Sheet | null;
    getSheets(): Sheet[];
    insertSheet(): Sheet;
    insertSheet(sheetIndex: number): Sheet;
    insertSheet(sheetName: string): Sheet;
    insertSheet(sheetName: string, sheetIndex: number): Sheet;
    deleteSheet(sheet: Sheet): void;
    moveActiveSheet(pos: number): void;
    moveSheet(srcIndex: number, desIndex: number): void;
    // To duplicate a worksheet, call sheet.copyTo(newName) on the Sheet itself —
    // Spreadsheet has no copySheet().
  }

  class Sheet {
    getName(): string;
    getSheetId(): string;
    /** 1-based position of this worksheet in the workbook. */
    getIndex(): number;

    /** GRID SIZE — how many rows/columns this sheet HAS (e.g. 1000 x 26 on a new
     *  sheet, whether or not anything is written there). */
    getMaxRows(): number;
    getMaxColumns(): number;
    /** USED RANGE — the last row/column that actually HAS CONTENT; 0 on an empty
     *  sheet. This is what you want for "read all the data" and for
     *  "append after the existing rows":
     *    sheet.getRange(1, 1, sheet.getLastRow(), sheet.getLastColumn()).getValues()
     *    sheet.getRange(sheet.getLastRow() + 1, 1, n, m).setValues(rows)
     *  The one-liner above is only safe for SMALL sheets — a single read is capped
     *  at 24 blocks (~12000 rows of one column) and throws above that.
     *  See "Reading large ranges" below before reading a tall sheet.
     *  Do NOT confuse the two: on a fresh 1000-row sheet holding 3 rows of data,
     *  getMaxRows() is 1000 and getLastRow() is 3. */
    getLastRow(): number;
    getLastColumn(): number;
    /** Rename this worksheet (name: up to 31 chars). This is the ONLY way to rename —
     *  do NOT create a new sheet and delete the old one (that also fails when the file
     *  has a single visible sheet). Chainable: returns this sheet. */
    setName(name: string): Sheet;
    /** Duplicate this worksheet; newName is optional (max 31 chars).
     *  NOT GAS-compatible: unlike Apps Script this takes the new sheet's NAME (not a
     *  Spreadsheet) and returns the NEW sheet's id (a string), not a Sheet — so
     *  `sheet.copyTo(ss).setName(x)` throws. Pass the id to
     *  `SpreadsheetApp.getActiveSpreadsheet().getSheetById(id)` to get the Sheet object.
     *  Note: this is a method on Sheet, NOT `spreadsheet.copySheet(sheet, name)`. */
    copyTo(newName?: string): string;

    getRange(a1Notation: string): Range;
    getRange(row: number, col: number): Range;
    getRange(row: number, col: number, numRows: number, numCols: number): Range;
    getDataRange(): Range;
    getActiveRange(): Range;

    /** Read the merged regions of this sheet. This is how you inspect merges —
     *  there is no other way. All four optional params are 1-based and default to
     *  the whole sheet; a merge that merely OVERLAPS the queried box is included.
     *  Returns Range objects — chain .getA1Notation() / .breakApart() / .getValue(),
     *  or .getRow() / .getColumn() / .getNumRows() / .getNumColumns() for plain
     *  coordinates. getMerges() is an alias of getMergedRanges().
     *  Example: for (const r of sheet.getMergedRanges()) r.breakApart(); */
    getMergedRanges(startRow?: number, startCol?: number, numRows?: number, numCols?: number): Range[];
    getMerges(startRow?: number, startCol?: number, numRows?: number, numCols?: number): Range[];

    /** Clear the WHOLE worksheet: clear() erases content and styling,
     *  clearContents() erases content only. To clear part of a sheet, use
     *  `sheet.getRange(...).clear()` / `.clearContent()` instead.
     *  Chainable: returns this sheet. */
    clear(): Sheet;
    clearContents(): Sheet;

    /** Read the FULL configuration of an existing pivot table — the ONLY way to
     *  inspect one (PivotTable is write-only). Return shape PivotTableDetailData and
     *  the full inspect guidance live in the **sheet-pivot-tables** reference. */
    getPivotTableDetail(pivotTableId?: string, pivotTableName?: string): PivotTableDetailData;
    getObjectList(objectTypes?: string[], namePattern?: string): SheetObjectData[];
    /** Hydrate an existing pivot table by id (or name) into a pre-populated PivotTable
     *  instance for modification (then add*/set* → update() to commit). Use this — NOT
     *  createPivotTable with the same id. Modify-vs-rebuild pattern: sheet-pivot-tables. */
    getPivotTable(pivotTableIdOrName: string): PivotTable;

    insertRows(row: number, numRows?: number): void;
    deleteRow(row: number): void;
    deleteRows(row: number, numRows: number): void;
    /** Move `numRows` rows starting at `startRow` so they land before `destinationRow` (all 1-based). */
    moveRows(startRow: number, numRows: number, destinationRow: number): void;
    /** Move `numColumns` columns starting at `startColumn` so they land before `destinationColumn` (all 1-based). */
    moveColumns(startColumn: number, numColumns: number, destinationColumn: number): void;

    /** Row height APIs — unit: pixels (px). Both parameters and return values are in pixels. */
    getRowHeight(row: number): number;
    setRowHeight(row: number, height: number): void;
    setRowHeights(startRow: number, numRows: number, height: number): void;
    setRowHeightsForced(startRow: number, numRows: number, height: number): void;

    insertColumns(col: number, numCols?: number): void;
    deleteColumn(col: number): void;
    deleteColumns(col: number, numCols: number): void;
    /** Column width APIs — unit: pixels (px). Both parameters and return values are in pixels. */
    getColumnWidth(col: number): number;
    setColumnWidth(col: number, width: number): void;
    setColumnWidths(startCol: number, numCols: number, width: number): void;

    /** Freeze top N rows (0 = unfreeze rows, keeps column freeze). */
    setFrozenRows(rows: number): void;
    /** Freeze left N columns (0 = unfreeze columns, keeps row freeze). */
    setFrozenColumns(columns: number): void;

    /** Hide / show rows, columns and sheet tab. Indexes are 1-based; data is preserved (UI-only). */
    hideRow(rowIndex: number): Sheet;
    hideRows(rowIndex: number, numRows?: number): Sheet;
    showRows(rowIndex: number, numRows?: number): Sheet;
    unhideRow(rowIndex: number): Sheet;
    hideColumn(columnIndex: number): Sheet;
    hideColumns(columnIndex: number, numColumns?: number): Sheet;
    showColumns(columnIndex: number, numColumns?: number): Sheet;
    unhideColumn(columnIndex: number): Sheet;
    hideSheet(): Sheet;
    showSheet(): Sheet;
    isSheetHidden(): boolean;

    newChart(
      drawingId: string,
      chartType: string,   // value list incl. combo presets: see charts-visual
      dataRange: Range,
      anchorRow: number, anchorCol: number,
      offsetX: number, offsetY: number,
      width: number, height: number,
      options?: ChartOptions,
    ): EmbeddedChart;
    /** Compatibility no-op: chart is already inserted at newChart() time. */
    insertChart(chart: EmbeddedChart): void;
    // Delete: sheet.removeChart(chartId). Id lookup + reuse pitfalls: charts-delete.
    removeChart(chartId: string): void;
    // Insert an image at the specified cell position. row and col are 1-based.
    // imageData: base64 encoded image data or data URI (e.g. "data:image/png;base64,...")
    insertImage(row: number, col: number, imageData: string): void;
    // To DELETE an image
    // Note: this API is not yet implemented;
    removeImage(drawingId: string): void;
    getCharts(): EmbeddedChart[];
    // columns[].col: 0-based column index, e.g., to filter the 4th column, pass col = 3
    // Creates the filter on this range. Call this FIRST before setColumnFilterCriteria —
    // a filter must exist for criteria to take effect. Throws if the sheet already has one.
    createFilter(range: Range): Filter;
    // Lazy handle to this sheet's filter. ALWAYS returns a non-null object even when no
    // filter exists, so a non-null return does NOT mean a filter is present. Prefer calling
    // createFilter() first (catch its "already has a filter" error) over getFilter() truthiness.
    getFilter(): Filter;
    getSheetName(): string;

    // [CLOUD_AGENT only]
    // Mark a range as private (content masked from viewers); isUnset=true removes the marking. All params 1-based.
    setPrivateRange(startRow: number, startCol: number, numRows: number, numCols: number, isUnset?: boolean): void;
    // Set dropdown/multi-select validation on A1-notation ranges; type NONE removes the rule.
    setDataValidation(type: "LIST" | "MULTIPLE_LIST" | "NONE", ranges: string[], options?: Array<{ text: string; id?: string; text_color?: string; bg_color?: string }>): void;
    // Set dropdown/multi-select validation on whole columns; colIndexes are 0-based [{start,end}]; ignoreRows skips header rows.
    setDataValidationByColumns(type: "LIST" | "MULTIPLE_LIST" | "NONE", colIndexes: Array<{ start: number; end: number }>, ignoreRows?: number, options?: Array<{ text: string; id?: string; text_color?: string; bg_color?: string }>): void;

    /** Add a new conditional format rule. Returns { cf_id } — save for update/remove. */
    addConditionalFormat(params: AddConditionalFormatParams): { cf_id: string };
    /** Query existing rules on this sheet (optionally filtered by range). Returns brief info only (cf_id/priority/ranges) — rule details are NOT returned. */
    getConditionalFormats(params: GetConditionalFormatsParams): { items: ConditionalFormatItem[] };
    /** Full replacement of an existing rule identified by cf_id. */
    updateConditionalFormat(params: UpdateConditionalFormatParams): void;
    /** Remove one rule by cf_id, or all rules when is_remove_all: true. */
    removeConditionalFormat(params: RemoveConditionalFormatParams): void;

    // [CLOUD_AGENT only]
    /** Protect a range or the entire sheet. Returns { protect_range_id } — save for update/delete. */
    addProtectRange(params: AddProtectRangeParams): { protect_range_id: string };
    /** Change the protected range identified by protect_range_id. */
    updateProtectRange(params: UpdateProtectRangeParams): void;
    /** Remove a protection by protect_range_id. */
    deleteProtectRange(params: DeleteProtectRangeParams): void;
    /** List all protections on this sheet. */
    getProtectRanges(params: GetProtectRangesParams): { items: ProtectRangeItem[] };
  }

  /** Return shape of Range.auditFormulaConsistency(). All row/col indices are 0-based. */
  interface FormulaConsistencyReport {
    /** true when every formula cell shares the majority R1C1 pattern and there are no gaps. */
    is_consistent: boolean;
    total_formula_cells: number;
    distinct_patterns: number;
    majority_pattern: string;
    majority_count: number;
    groups: Array<{ r1c1: string; count: number; cells: Array<{ row: number; col: number }> }>;
    outliers: Array<{ row: number; col: number; r1c1: string }>;
    gaps: Array<{ row: number; col: number }>;
  }

  interface Range {
    getSheetId(): string;
    getRow(): number;
    getColumn(): number;
    getNumRows(): number;
    getNumColumns(): number;
    getA1Notation(): string;

    getValue(): string | number | boolean | null;
    getValues(): any[][];
    setValue(value: any): void;
    setValues(values: any[][]): void;
    /** Three different erasers — pick by what must survive:
     *  clear() erases content AND styling, clearContent() erases values and
     *  formulas but keeps styling, clearFormat() erases styling but keeps
     *  content. All three are chainable. */
    clear(): Range;
    clearContent(): Range;
    clearFormat(): Range;

    setFormula(formula: string): void;
    setFormulas(formulas: string[][]): void;
    getFormula(): string;
    getFormulas(): string[][];
    /** Audit this rectangle for formula-pattern consistency (R1C1-normalised):
     *  flags outlier formulas and non-formula gaps. Useful for the audit-spreadsheet flow. */
    auditFormulaConsistency(): FormulaConsistencyReport;

    getNumberFormat(): string;
    getNumberFormats(): string[][];
    setNumberFormat(fmt: string): void;
    setNumberFormats(fmts: string[][]): void;

    getBackground(): string;
    getBackgrounds(): string[][];
    setBackground(color: string | null): void;
    setBackgrounds(colors: (string | null)[][]): void;

    setFontColor(color: string): void;
    setFontColors(colors: string[][]): void;
    getFontColor(): string;
    getFontColors(): string[][];
    setFontFamily(family: string): void;
    setFontFamilies(families: string[][]): void;
    getFontFamily(): string;
    getFontFamilies(): string[][];
    setFontSize(size: number): void;
    setFontSizes(sizes: number[][]): void;
    getFontSize(): number;
    getFontSizes(): number[][];
    setFontLine(line: "underline" | "line-through" | "none"): void;
    setFontLines(lines: string[][]): void;
    getFontLine(): string;
    getFontLines(): string[][];
    setFontWeight(weight: "bold" | "normal"): void;
    setFontWeights(weights: string[][]): void;
    getFontWeight(): string;
    getFontWeights(): string[][];
    setFontStyle(style: "italic" | "normal"): void;
    setFontStyles(styles: string[][]): void;
    getFontStyle(): string;
    getFontStyles(): string[][];
    setWrap(wrap: boolean): void;
    setWraps(wraps: boolean[][]): void;
    getWrap(): boolean;
    getWraps(): boolean[][];
    setVerticalAlignment(align: "top" | "middle" | "bottom"): void;
    setVerticalAlignments(aligns: string[][]): void;
    getVerticalAlignment(): string;
    getVerticalAlignments(): string[][];

    setHorizontalAlignment(align: "left" | "center" | "right" | "general" | "general-left" | "justify"): void;
    setHorizontalAlignments(aligns: string[][]): void;
    getHorizontalAlignment(): string;
    getHorizontalAlignments(): string[][];

    merge(): void;
    mergeAcross(): void;
    mergeVertically(): void;
    breakApart(): void;
    /** Merge regions overlapping this range (may extend outside it), and whether
     *  there is any. The read side of merging lives here and on Sheet — do NOT
     *  reach for other GAS-style spellings, they DO NOT EXIST. */
    getMergedRanges(): Range[];
    isPartOfMerge(): boolean;

    /** Create a pivot table, then configure via add*/set* → update(). Full usage in
     *  the **sheet-pivot-tables** reference. */
    createPivotTable(id: string, sourceData: Range, name?: string): PivotTable;

    getBorder(): { top: BorderSide | null; bottom: BorderSide | null; left: BorderSide | null; right: BorderSide | null };
    getBorders(): { top: BorderSide | null; bottom: BorderSide | null; left: BorderSide | null; right: BorderSide | null }[][];
    setBorder(
      top: boolean, left: boolean, bottom: boolean, right: boolean,
      vertical: boolean, horizontal: boolean, color?: string, style?: string,
    ): Range;
    setBorders(borders: { top: BorderSide | null; bottom: BorderSide | null; left: BorderSide | null; right: BorderSide | null }[][]): Range;
    insertCells(shiftDimension: "ROWS" | "COLUMNS"): Range;
    deleteCells(shiftDimension: "ROWS" | "COLUMNS"): void;
    /** Sort the ROWS of this range in place. ⚠️ Only columns INSIDE this range move
     *  with each row; columns outside the range stay put. Sorting a range narrower
     *  than the data block TEARS every record horizontally (irreversible) — the sort
     *  range MUST span the block's full width. Boundary depends on read_table's
     *  `truncated`: false → start_col..end_col; true → end_col is only the visible
     *  cutoff (= visible_end_col), widen to actual_end_col and confirm the real edge
     *  before sorting (same for end_row vs actual_end_row). */
    sort(column: number): Range;
    sort(spec: { column: number; ascending?: boolean }): Range;
    sort(specs: { column: number; ascending?: boolean }[]): Range;
  }

  class Utility {
    static sleep(ms: number): void;
    static describeSheets(ss: Spreadsheet): { name: string; rows: number; cols: number }[];

    static readDataInBatches(
      sheet: Sheet, startRow: number, numCols: number,
      cb: (rows: any[][]) => void, batchSize?: number,
    ): void;

    static groupBy(data: any[][], keyCol: number, valueCol: number): {
      key: any; sum: number; count: number; avg: number;
    }[];
    static validateData(data: any[][], keyCols: number[]): {
      emptyRows: number[]; duplicateRows: number[];
    };

    static deleteRowsWhere(
      sheet: Sheet, info: TableInfo,
      predicate: (row: any[]) => boolean,
    ): { deleted: number; remaining: number };
    static keepRowsWhere(
      sheet: Sheet, info: TableInfo,
      predicate: (row: any[]) => boolean,
    ): { kept: number; removed: number };
    static deduplicateRows(sheet: Sheet, info: TableInfo, keyCol: number): {
      kept: number; removed: number;
    };

    static findAndReplace(sheet: Sheet, info: TableInfo, search: string, replace: string): number;
    static copyRowsTo(
      src: Sheet, dst: Sheet, srcInfo: TableInfo,
      predicate: (row: any[]) => boolean,
    ): number;
  }

  interface BorderSide {
    color: string;  // hex color e.g. "FF000000"
    style: string;  // "SOLID" | "SOLID_MEDIUM" | "SOLID_THICK" | "DASHED" | "DOTTED" | "DOUBLE"
  }

  interface TableInfo {
    startRow: number; startCol: number; endRow: number; endCol: number;
    orientation: "ROW" | "COLUMN" | "MATRIX";
    headers: string[]; numCols: number; numDataRows: number;
    cells: Record<string, any>;
    formulas: Record<string, string>;
    formats: Record<string, string>;
    hasMore: boolean;
  }

  enum FilterCriteriaType {
    VALUE = 0,
    COLOR = 1,
    CONDITION = 2,
  }

  interface FilterColumnCriteria {
    // col: 0-based column index, e.g., to filter the 4th column, pass col = 3
    col: number;
    criteria: {
      type: FilterCriteriaType;
      visible_values: string[];
    };
  }

  // ChartOptions / ChartTextStyle full type shapes live in charts-visual (single
  // source of truth; not duplicated here to avoid drift). Used by newChart options?
  // (above) and setOptions/getOptions (below). Read charts-visual before filling them.

  class EmbeddedChart {
    getChartType(): string;
    getDrawingId(): string;
    getTitle(): string;
    /** Top-left anchor row (0-based); -1 when unknown. Use with getCharts() to
     *  probe existing charts' positions before placing a new one. */
    getAnchorRow(): number;
    /** Top-left anchor column (0-based); -1 when unknown. */
    getAnchorCol(): number;
    /** Chart width in px; -1 when the backend does not report a size. */
    getWidth(): number;
    /** Chart height in px; -1 when the backend does not report a size. */
    getHeight(): number;
    setOptions(options: ChartOptions): EmbeddedChart;
    getOptions(): ChartOptions;
    setChartType(chartType: string): EmbeddedChart;
    setTitle(title: string): EmbeddedChart;
    setPosition(anchorRow: number, anchorCol: number, offsetX: number, offsetY: number): EmbeddedChart;
    setSize(width: number, height: number): EmbeddedChart;
    setDataRange(range: Range): EmbeddedChart;
    getDataRange(): Range;
    remove(): void;
  }

  // class PivotTable (WRITE-ONLY pivot config class) — full declaration + create/
  // inspect/modify usage are the single source of truth in sheet-pivot-tables (not
  // duplicated here to avoid drift); Read it before any pivot work (§4.3.3). To READ
  // a pivot use sheet.getPivotTableDetail() (above); GAS-style getPivotTables() /
  // getPivotTableById() / getRowGroups() DO NOT EXIST.

  class Filter {
    remove(): void;
    /** Set the "visible values" criteria for one column (columnPosition is 1-based).
     *  An empty visibleValues array hides every value in that column; columns not
     *  passed keep their existing criteria.
     *  IMPORTANT: Requires a filter to already exist (created via Sheet.createFilter(range));
     *  on a sheet with no filter this call is a silent no-op. */
    setColumnFilterCriteria(columnPosition: number, visibleValues: string[]): void;
  }

  interface AdapterGridRange {
    sheet_id: string;
    start_row_index: number;
    start_col_index: number;
    end_row_index: number;
    end_col_index: number;
  }

  interface ChartObjectInfoData {
    chart_type: string;
  }

  interface PivotTableObjectInfoData {
    row_group_count: number;
    column_group_count: number;
    value_count: number;
  }

  interface TableObjectInfoData {
    has_header: boolean;
    column_count: number;
  }

  interface FloatImageObjectInfoData {
    width: number;
    height: number;
  }

  interface SheetObjectData {
    object_id: string;
    object_type: string;
    name: string;
    display_range?: AdapterGridRange;
    data_range?: AdapterGridRange;
    chart_info?: ChartObjectInfoData;
    pivot_table_info?: PivotTableObjectInfoData;
    table_info?: TableObjectInfoData;
    float_image_info?: FloatImageObjectInfoData;
  }

  // interface PivotTableDetailData — the shape returned by Sheet.getPivotTableDetail()
  // (pivot_table_id / pivot_table_name / anchor_row|col (1-based) / row_group_columns /
  // column_group_columns / pivot_values / filters / source_data_range (1-based, closed)).
  // The full field-by-field declaration points to the **sheet-pivot-tables** reference,
  // which is always loaded before pivot work (§4.3.3); it is not duplicated here.

  type ConditionalFormatOp =
    | "GT" | "LT" | "GTE" | "LTE" | "EQ" | "NEQ"
    | "BETWEEN" | "NOT_BETWEEN"
    | ">" | "<" | ">=" | "<=" | "==" | "!=";

  interface ConditionalFormatStyle {
    /** Hex color with leading #, e.g. "#FF0000" */
    font_color?: string;
    /** Hex color with leading #, e.g. "#FFFF00" */
    bg_color?: string;
    bold?: boolean;
    italic?: boolean;
    underline?: boolean;
    strikethrough?: boolean;
  }

  interface ConditionalFormatRule {
    /** Rule type — determines which extra sub-object is required. */
    type:
      | "CF_CELL_IS"        // requires cell_is
      | "CF_UNIQUE_VALUES"  // no extra fields
      | "CF_DUPLICATE_VALUES" // no extra fields
      | "CF_TOP10"          // requires top10
      | "CF_ABOVE_AVERAGE"; // optional above_average sub-object
    /** Required when type === "CF_CELL_IS" */
    cell_is?: {
      op: ConditionalFormatOp;
      /** One formula for single-value ops; two formulas for BETWEEN / NOT_BETWEEN. */
      formulas: string[];
    };
    /** Required when type === "CF_TOP10" */
    top10?: {
      /** Number of top/bottom items or percentage points (1–1000). */
      rank: number;
      /** true = bottom N instead of top N */
      bottom?: boolean;
      /** true = treat rank as a percentage */
      percent?: boolean;
    };
    /** Optional when type === "CF_ABOVE_AVERAGE" */
    above_average?: {
      /** true = above average (default); false = below average */
      above_average?: boolean;
      /** true = include cells equal to the average */
      equal_average?: boolean;
      /** Standard deviation multiplier (0 = use mean directly) */
      std_dev?: number;
    };
    /** At least one style field must be set. */
    style: ConditionalFormatStyle;
  }

  interface AddConditionalFormatParams {
    /** Range strings — each entry is "SheetID$A1:B100" or plain "A1:B100". */
    ranges: string[];
    rule: ConditionalFormatRule;
  }

  interface GetConditionalFormatsParams {
    /** Optional: filter results to rules that overlap these ranges. */
    ranges?: string[];
  }

  /** Brief info only — the full rule (type/style/params) is NOT echoed back by getConditionalFormats. */
  interface ConditionalFormatItem {
    cf_id: string;
    priority: number;
    ranges: string[];
  }

  interface UpdateConditionalFormatParams {
    cf_id: string;
    ranges: string[];
    rule: ConditionalFormatRule;
  }

  interface RemoveConditionalFormatParams {
    /** Remove a specific rule by id. Mutually exclusive with is_remove_all. */
    cf_id?: string;
    /** true = remove ALL rules on the sheet. Mutually exclusive with cf_id. */
    is_remove_all?: boolean;
  }

  // [CLOUD_AGENT only]
  interface ProtectRangeCoord {
    /** 0-based row index (closed interval). */
    start_row: number;
    /** 0-based column index (closed interval). */
    start_col: number;
    end_row: number;
    end_col: number;
  }

  interface AddProtectRangeParams {
    sheet_id: string;
    /** Protect a specific cell range. Mutually exclusive with whole_sheet. */
    range?: ProtectRangeCoord;
    /** true = protect the entire sheet. Mutually exclusive with range. */
    whole_sheet?: boolean;
  }

  interface UpdateProtectRangeParams {
    sheet_id: string;
    protect_range_id: string;
    /** New range to protect. Mutually exclusive with whole_sheet. */
    range?: ProtectRangeCoord;
    /** Forward-compat flag; the current backend requires `range` and may ignore this field. */
    whole_sheet?: boolean;
  }

  interface DeleteProtectRangeParams {
    sheet_id: string;
    protect_range_id: string;
  }

  interface GetProtectRangesParams {
    sheet_id: string;
  }

  interface ProtectRangeItem {
    protect_range_id: string;
    /** Present when a specific range is protected (not whole_sheet). */
    range?: ProtectRangeCoord;
    /** true when the entire sheet is protected. */
    whole_sheet?: boolean;
  }
}
```

## Reading large ranges

A single `getValues()` / `getFormulas()` / `getBackgrounds()` call is capped at
**24 blocks**, a block being 500 rows x 20 columns — roughly 12000 rows of one
column. Over the cap the call throws (it never silently truncates) and the error
tells you how to split it.

Read in chunks and aggregate as you go, keeping the aggregate rather than the rows.
Do not shrink the chunk "to be safe": every read re-assembles the whole document
upstream, so smaller chunks multiply the cost instead of spreading it.

## Key Constraints

- All batch setter methods require 2D arrays with dimensions exactly matching the target `Range`
- `range.clearContent()` erases content and keeps styling; `range.clear()` erases content **and** styling; `range.clearFormat()` erases styling only; `sheet.clear()` / `sheet.clearContents()` do the same over the whole worksheet. `setValue(null)` writes the literal string `"null"`
- After `setFormula()`, verify the result and fall back if the formula errors
- Delete columns from back to front to avoid index shifting
- `groupBy` and `deduplicateRows` use **0-based** column indices
- `newChart()` uses **0-based** `anchorRow` and `anchorCol`
- Color values must be hex strings with a leading `#`

## API Constraint

- You may **ONLY** use APIs documented in this API Reference, in a reference file you have read (e.g. the `charts-visual` / `charts-create` reference), or in currently loaded skills
- Do **NOT** rely on prior knowledge of any API — if it is not in the API Reference, a reference file you have read, or a loaded skill, it does not exist
- Calling an undocumented API will cause a runtime error
- If the required API does not exist, use JavaScript logic with existing APIs to achieve the goal (e.g., sort data in JS array then write back with setValues). Do NOT guess or invent API methods.
