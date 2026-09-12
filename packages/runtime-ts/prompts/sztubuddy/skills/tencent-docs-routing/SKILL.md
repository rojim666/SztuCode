---
name: tencent-docs-routing
description: Load this Skill before handling local Office/WPS files such as doc/docx/dot/wps/wpt, xls/xlsx/xlt/csv/tsv, or ppt/pptx/pps/pot, and before creating a new local document, spreadsheet, or presentation. Load first whenever the user uploads, mentions, previews, edits, or asks to create such a local file, to decide whether to use the local office editing Skill, the local spreadsheet agent, the spreadsheet generation Skill, or the PPT generation Skill. Text-based outputs such as speech scripts, talking points, copywriting, summaries, reports, or meeting minutes should default to local DOCX unless the user explicitly specifies another local format such as markdown or plain text. Other file types are out of scope.
author: Tencent Docs
version: "0.1.2"
---

# Local Office/WPS Routing

> **This is the gate you MUST read before handling local Office/WPS files — doc/docx/dot/wps/wpt, xls/xlsx/xlt/csv/tsv, or ppt/pptx/pps/pot — AND before generating/creating any new local document, spreadsheet, or presentation.** This Skill only describes local file operations. It routes **content** work only — reading a document's content into context, editing, creating, transforming, and the like. Simply opening, previewing, or presenting a document for the user to *view* is the host's preview/present surface, not content work — call the host preview/present tool directly instead of routing it through this Skill.

## Host document context

The host injects a `<tencent_docs_editor_context>` block that surfaces local documents (e.g. `<active_document type="local" .../>`, `<local_files>`). Route each surfaced document by the file-type rules below.

If the context block already injected a `file_id` for a document, follow the **Injected `file_id`** rule in [file_id resolution](#file_id-resolution-local-documents).

## Supported Local Formats

Use these extensions to decide whether this routing Skill applies:

| Type | Supported local file extensions |
|---|---|
| doc | `.doc` `.dot` `.wps` `.wpt` `.docx` `.dotx` `.docm` `.dotm` |
| sheet | `.xls` `.xlt` `.xlsx` `.xltx` `.xlsm` `.xltm` `.csv` `.tsv` |
| slide | `.ppt` `.pps` `.pot` `.pptx` `.ppsx` `.potx` `.pptm` `.ppsm` `.potm` |

Macro-enabled files (`.docm` `.dotm` `.xlsm` `.xltm` `.pptm` `.ppsm` `.potm`) can be opened as their corresponding doc/sheet/slide type, but macros are not executed. WPS-specific `.et` `.ett` `.dps` `.dpt` are not supported; ask the user to save them as `.xlsx` or `.pptx` first.

## New Local File Creation

When the user asks to **generate / create / produce** a new document, spreadsheet, or presentation, produce a local Office/WPS-type file and route by file type.

### Format classification (prerequisite step)

When the output the user requests is essentially structured textual content — such as speech scripts, talking points, copywriting, summaries, reports, or meeting minutes — always classify it as a doc first, then apply the local DOCX creation path.
Do not default to Markdown or plain text.
Only when the user explicitly specifies another local non-DOCX format (e.g. "generate markdown" or "plain text is fine") is this rule overridden.
This rule does not affect outputs that clearly belong to sheet (e.g. "make a spreadsheet") or ppt (e.g. "make a PPT").

## Existing Local Documents

> Note: This section applies to **existing local** documents that need to be read or edited. For **new** document creation, see "New Local File Creation" above.

Every task resolves by file type and task nature:

1. **Local doc/slide single-file edits** → load the **`tencent-local-office-edit`** Skill and operate through it.
2. **Local PPT creation from source materials** → use the **`tencent-pptx`** Skill.
3. **Local DOCX/Word creation from scratch, or an abstract whole-document beautification of an existing DOCX/Word file** → use the **`tencent-docx`** plugin (from-scratch creation → `full_pipeline`; whole-document abstract beautification → `beauty_only`). See the DOCX/Word sections below for the exact triggers and out-of-scope cases.
4. **Creating a new spreadsheet when NO source spreadsheet file is involved** (whether from pure text or based on referenced PDF/DOCX/PPTX materials) → use the **`tencent-docs-sheet-generation`** Skill. See "Creating a new spreadsheet (no source spreadsheet file)" below.
5. **Any local spreadsheet task where a source spreadsheet file IS involved** — editing it, analyzing it, or generating a new sheet out of it — → follow the sheet routing rules below (never `tencent-docs-sheet-generation`).

## Creating a new PPT from source materials

When the user's intent is to create a new PPT based on source materials (e.g. DOCX, XLSX, PPT, PDF, etc.), strictly use the `tencent-pptx` Skill. This Skill has efficient built-in material parsing and processing capabilities; avoid parsing those materials by any other means.

## Creating a new spreadsheet (no source spreadsheet file)

Whenever the user asks to **produce a new spreadsheet** — signaled by authoring verbs such as 生成 / 制作 / 新建 / 做一份…表 / 整理成 Excel applied to a spreadsheet — AND **no** source spreadsheet file (`.xls` `.xlt` `.xlsx` `.xltx` `.xlsm` `.xltm` `.csv` `.tsv`) is involved, strictly use the `tencent-docs-sheet-generation` Skill. The decisive condition is the **absence of a source spreadsheet file**, not whether reference materials are attached: the content requirement may be pure text, or it may reference local materials — **only** local PDF, DOCX, or PPTX files are supported as reference materials here (local `.csv` / images / archives / other types are not). In every case hand the raw requirement and any referenced materials to the Skill and let it parse them; do **not** pre-parse those supported (PDF/DOCX/PPTX) materials by any other means.

This route requires that **no source spreadsheet file is involved**. Out of scope (do **not** send here):
- A source spreadsheet file (`.xlsx` / `.xls` / `.csv` / `.tsv`) is involved — **regardless of whether the wording sounds like "creation"**, e.g. "summarize this xlsx into a new sheet" / "根据这个表再生成一份新表". Once any source spreadsheet file is present, the task follows the sheet routing rules below (`tencent-docs-sheetagent` for data-dependent work, the `tencent-local-office-edit` Skill for deterministic edits), never `tencent-docs-sheet-generation`. The `tencent-docs-sheet-generation` Skill itself bails out and asks for re-routing when a source spreadsheet is present.
- The requested output is not a spreadsheet (doc / ppt / text) — follow its own creation route above.
- The only reference material is a type this Skill cannot parse — e.g. an **image**, an archive, or any format other than PDF/DOCX/PPTX (note: `.csv` / `.tsv` are source spreadsheet files, routed above, not references). Do **not** hand such material to the Skill, since it parses only PDF/DOCX/PPTX. Instead read its content into a plain-text requirement yourself first (e.g. read the numbers out of an image), then route that resulting pure-text request here as a normal no-source-file spreadsheet creation. If no usable content can be extracted, tell the user which inputs are supported (plain text, or PDF/DOCX/PPTX references) rather than routing here.

## Local DOCX/Word creation from scratch

Whenever the user asks to **produce a new DOCX/Word file from zero** — signaled by authoring verbs such as 生成 / 写 / 起草 / 撰写 / 新建 / 重写 (重写 is treated as from-scratch creation here) applied to a document — strictly use the `tencent-docx` plugin. This is not restricted to specialized verticals: it covers ordinary everyday documents as well as recognizable professional genres such as research report (研报), annual report (年报), academic paper (论文), official/government document (公文), contract (合同), business report (商务报告), meeting minutes (会议纪要). In every case the plugin produces a complete document with an auto-generated cover page and professional, context-appropriate layout/typography; avoid assembling such documents by any other means.

This route is for **from-scratch creation only**: the plugin does **not** ingest source materials (DOCX, XLSX, PPT, PDF, etc.). If the user supplies source materials to be turned into a document, do not route here — fall back to the standard DOCX/Word creation path via the `tencent-local-office-edit` Skill. Editing an existing DOCX/Word file likewise stays with `tencent-local-office-edit`.

Concretely, the Orchestrator inside `tencent-docx` MUST decide `full_pipeline` directly at Stage 0 — no deliberation, no extra intent probing, no detour through lighter stages.

## Whole-document beautification of an existing DOCX (abstract styling)

When the user has already provided a single content document A AND asks for an **abstract, whole-document** beautification — expressions like "美化一下" / "更专业" / "更好看" / "排版优化" that require the AI to make design decisions without naming specific style values — AND **no** separate independent style-reference document B is attached, AND the request does **not** scope the beautification to a specific part of the document (e.g. "美化这个表格" / "美化这一段" / "调整第 X 节的样式"), use the `tencent-docx` plugin.

In this case the Orchestrator inside `tencent-docx` MUST decide `beauty_only` directly at Stage 0 — no deliberation, no extra intent probing, no detour through other stages.

Out of scope for this route (do **not** send here):
- The user provided a style-reference document B alongside A (that is a different routing decision, not this one).
- The user scoped the beautification to a specific fragment — a named table, a paragraph, a section, a page, etc. Localized style edits stay with the `tencent-local-office-edit` Skill.
- The user specified concrete style values (fonts, sizes, colors, spacing, etc.) — that is a direct edit, not an abstract beautification.

## Sheet Files (spreadsheets)

**First, is a source spreadsheet file involved?** If **no** source spreadsheet file is involved (a new spreadsheet, whether from pure text or from referenced PDF/DOCX/PPTX materials), it does not belong here — route it to the `tencent-docs-sheet-generation` Skill (see "Creating a new spreadsheet (no source spreadsheet file)" above). Everything below assumes a source spreadsheet file **IS** involved; any such task — including generating a new sheet out of an existing one — stays on the sheet routes below (`tencent-docs-sheetagent` / `tencent-local-office-edit`), never `tencent-docs-sheet-generation`.

Resolve local sheet tasks by task nature. The `tencent-local-office-edit` Skill is allowed only for a small, bounded set of deterministic edits; complex or data-dependent local tasks MUST use `tencent-docs-sheetagent`.

**Decide from the request TEXT alone, never from the data.** Apply this one test to the user's wording:

> Is the request a direct, deterministic edit — its operation type is fixed by the wording (format / border / merge / insert-delete rows·cols·cells / row-height·col-width / filter / sort / sheet add-delete-move / a formula written into a named cell) — and its target is either an explicit address or a label you can pin down by a single match?

- **Yes** → operate through the `tencent-local-office-edit` Skill.
- **Other sheet content work** → `tencent-docs-sheetagent`. No deliberation, no investigation.

Match the work to the tool:

| Route here | When the local sheet task is |
|------------|------------------|
| `tencent-local-office-edit` Skill | A semantically unambiguous read/write completing in **a small, bounded set of deterministic calls** — e.g. reading or writing one specific cell/range, sorting one column (operate through the Skill) |
| `tencent-docs-sheetagent` | Data analysis · aggregation · pivot · stats, cross-sheet linkage, formula building, data cleaning, conditional formatting across ranges, or anything needing you to understand the data before deciding how to edit. For these local tasks, use `tencent-docs-sheetagent`; do not handle them through the `tencent-local-office-edit` Skill |

For local sheet files, the `tencent-local-office-edit` Skill is a right route for any direct, deterministic edit that passes the routing test above. Locating is reading the file only to find where the operation applies or what its current state is. This covers any lookup whose answer is a determinate address or value the file already contains. It is allowed on the local route and does not push the task to `tencent-docs-sheetagent`. Understanding the data — reading values to decide what the edit should be: what a previous edit did, why something renders wrong, which rows qualify under a condition you must infer, or how to aggregate / compare / clean — is the data-dependence test failing, and goes to `tencent-docs-sheetagent`. Diagnosis, comparison, and verification are the subagent's job, exactly like data discovery — they are not part of routing. Delegating means **invoking the `tencent-docs-sheetagent` skill first** — call the Skill tool with the name `tencent-docs-sheetagent` — and spawning the `sheet-agent` subagent only as it instructs; do **not** spawn `sheet-agent` directly, even though the subagent is visible on the Agent tool. `tencent-docs-sheetagent` counts as unavailable **only** if that Skill call itself fails with a not-found / unknown-skill error; only then fall back to the `tencent-local-office-edit` Skill.

**Atomic sheetagent delegation:** For one user request, if a local sheet task should enter `tencent-docs-sheetagent`, hand it the entire spreadsheet task — do not split the request by doing preparatory reads, partial writes, formatting, or cleanup through the `tencent-local-office-edit` Skill and then delegating only the remaining work. The only local calls allowed before delegating are the ones [file_id resolution](#file_id-resolution-local-documents) needs — nothing that touches document content; a new spreadsheet with **no source spreadsheet file involved** is not a sheetagent task at all — it follows the **Creating a new spreadsheet (no source spreadsheet file)** rule (route to the `tencent-docs-sheet-generation` Skill) instead. Once `tencent-docs-sheetagent` is the route (or even a candidate), resolve the `file_id`, then **invoke the `tencent-docs-sheetagent` skill and follow its delegation contract** — do not spawn the `sheet-agent` subagent directly — forwarding the resolved `file_id`, the absolute path, and the user's request verbatim; the subagent only consumes a live `file_id` and must not open files or resolve paths itself. If the task involves another spreadsheet (e.g. comparing with, or restoring formats from, an original file), resolve that file's `file_id` the same way and pass **both** ids with their paths — do not read or inspect either file's content yourself. Saving after the subagent finishes stays with you, not the subagent — per the `tencent-local-office-edit` flow.

Between resolving the `file_id` and delegating, make **no other** local call. Do not call `sheet_get_sheet_info`, do not read cells or ranges, do not pre-locate the data, and do not "look at the data first to understand it" — data discovery (sheets, headers, ranges) is the subagent's job, and any pre-reading splits the task (see [Atomic sheetagent delegation](#sheet-files-spreadsheets) above). If a plan you formed before reading this Skill included "read the data, then delegate", drop the read step. If the subagent rejects the `file_id` you passed, re-check it per [file_id resolution](#file_id-resolution-local-documents) and re-delegate; do **not** switch to reading the data yourself.

### Examples

> These illustrate the *pattern* — judge a request by which description fits, not by whether its wording matches an example.

**Examples → local `tencent-local-office-edit` Skill**
- Read / write / format a named cell or range — e.g. "Read A1:D10", "Set B2 to 100", "Bold A1"
- A deterministic operation whose target is a concrete, addressable part of the sheet  — e.g. "Sort the 'Price' column ascending", "Set all column widths to 120px"

**Examples → `tencent-docs-sheet-generation` Skill (no source spreadsheet file involved)**
- Pure-text requirement — e.g. "做一份 6 月销售统计表", "帮我生成一张项目排期表".
- Content referenced from a non-spreadsheet material — e.g. "根据这份 PDF 整理成一个 Excel 表格", "把这个 Word 里的数据做成表格" (hand the material to the Skill; do not pre-parse it).

**Examples → local `tencent-docs-sheetagent`**
- Generating a new sheet **out of an existing spreadsheet file** — e.g. "根据这个 xlsx 汇总出一张新表"; a source spreadsheet is involved, so it is sheetagent's job, not sheet-generation's, even though the wording says "生成".
- **Any** pivot-table create or edit — e.g. "Build a pivot table"; it always requires reading the source data first.
- Ambiguous scope that needs judgment — e.g. "Clean up this table".
- Layout restructuring — e.g. "Move this column"; it needs to read the current structure first.

## file_id resolution (local documents)

`file_id` identifies an open local editor instance — it always comes from the **`tencent-local-office-edit`** Skill's entry tools (`get_pool_status`, `open_file`, `create_*`); never invent one from a path or filename. This section only fixes **when** each entry applies; the calling style, workflow, and error handling are owned by that Skill's own documentation.

- **Injected `file_id`** — if the context block already injected one (e.g. `<active_document type="local" ... file_id="..."/>`), use it directly. The document already has a live host-owned editor/preview instance — do **not** reopen or re-present it.
- **Existing file, no injected id** — resolve it through the `tencent-local-office-edit` Skill's documented flow (`get_pool_status` to find an already-open instance, `open_file` otherwise), then do the content work through that Skill.
- **Brand-new document (no file on disk yet)** — there is nothing to resolve; do **not** call `get_pool_status` / `open_file` on a path that does not exist. Creating the file and its first save are owned by the routed Skill (e.g. `tencent-pptx`, `tencent-docs-sheet-generation`) or the host's create flow; once the file exists on disk, re-enter here for any subsequent edit.

## Showing a document to the user (preview)

Previewing is the **host's preview surface**, not a content channel and not part of [file_id resolution](#file_id-resolution-local-documents). Present a local document to the user, per the host's preview instructions, whenever they should see it:

- **After creating a new local document** through a routed Skill (e.g. `tencent-pptx`, `tencent-docs-sheet-generation`, `tencent-docs-sheetagent`), open it so the user can immediately see and work with the result.
- **After finishing edits** on a document that is not already visible to the user, once it is saved.

Do **not** re-preview a document the context block already injected with a live `file_id`: it already has a host-owned preview instance.
