---
name: design-rules
description: Single source of truth for ardot design editing — editing principles, coordinates, flexbox layout, text nodes, colors/fills, tables, images, effects, property quick reference, troubleshooting, post-generation validation pattern, and node property schema. 
metadata:
  tags: ardot, design, rules, flexbox, components, schema, validation
---

# Design Rules & Property Reference

Comprehensive rules for creating and editing .ardot designs. This is the single source of truth for editing principles, property rules, code patterns, node schema, and troubleshooting.

## Editing Principles

- After generating, validate with the schema and proceed or correct as needed.
- Use `capture_layout` and `capture_screenshot` periodically and at the end to verify design changes.
- Be thorough — make sure all task requirements are met. Verify after finishing.
- Follow `gap` and `padding` layout properties exactly on each component (buttons, tables, cards, etc.).
- If a property is not defined, treat it as 0 — do NOT hallucinate values.
- Combine multiple changes into a single tool call when possible.
- Keep each `batch_edit` call to **maximum 25 operations**. Split complex screens by logical sections.
- Favor copying existing content and updating it, rather than generating from scratch.
- Always place created/copied screens or components in empty areas. Never overlap.
- **IMPORTANT:** Every created node must have a meaningful `name`.
- **IMPORTANT:** Always call `locate_available_space` before inserting a node on the root page.

## Planning and Validation

- Create icons as components first, then insert instances with `I(parentId, {type: "ref", ref: "iconId"})`.
- Create reusable components as building blocks before assembling the main design.
- Create reusable variables for easier theme changes.
- After assembling design JSON, perform schema validation: check required properties, value constraints, and object relationships.
- Use `batch_read` to list reusable nodes in a design system frame to understand available components.

## Coordinates

- All coordinates are relative to the parent's top-left corner.
- `x` increases to the right, `y` increases downward.
- Child coordinates are always relative to their parent.

## Flexbox Layout

- **Always prefer flexbox layout** for arranging and sizing objects.
- When inserting a new frame, always explicitly set `width` and `height` — never assume auto layout.
- **Frame defaults at creation time**: a brand-new frame is `layout: "horizontal"` with `hug_contents` sizing on both axes — but only when you don't override either field.
- **Override caveat**: as soon as you explicitly set `layout` (to `horizontal`, `vertical` or `wrap`) without also setting `width` / `height`, sizing falls back to `FIXED`, not `hug_contents`. So if you want dynamic sizing alongside an explicit `layout`, set `width` / `height` (to `fill_container` or `hug_contents`) explicitly in the same call.
- Prefer `fill_container` or `hug_contents` over hardcoded pixel values.
- When using flexbox, **x/y on children are completely ignored**. To position a child in a flexbox container, set the child's `layoutPositioning` to `ABSOLUTE` (default is `AUTO`).
- `fill_container` is only valid when parent has flexbox layout.
- `hug_contents` is only valid on a node that itself has flexbox layout.
- A parent cannot use `hug_contents` if **all** direct children use `fill_container` — circular dependency.
- Padding affects ALL children uniformly. To offset one child, wrap it in a frame with padding (no margin in flexbox).
- `layout: "none"` makes children use absolute positioning — avoid unless necessary.
- Use `primaryAxisAlignItems: "CENTER"` + `counterAxisAlignItems: "CENTER"` to center children (only works for flexbox layout).
- Use `primaryAxisAlignItems: "SPACE_BETWEEN"` to distribute children to opposite ends (only works for flexbox layout).
- Setting layout to `"none"` will make all children use absolute positioning. Avoid using absolute positioning unless absolutely necessary.


### Layout Code Example


```javascript
parent=I("pageId", {type: "frame",name: "Parent Frame", layout: "vertical", width: 1920, height: 1080})
container=I(parent, {
  type: "frame",
  name: "Content Container",
  layout: "vertical",        // or "horizontal" or "none" for absolute
  gap: 16,                    // spacing between children
  padding: 24,                // uniform padding
  primaryAxisAlignItems: "CENTER",      // main axis alignment
  counterAxisAlignItems: "CENTER",      // cross axis alignment
  width: "fill_container",
  height: "hug_contents"
})
```

For repeating card layouts (product grids, feature cards, stat cards), use `layout: "wrap"` instead of manual row calculations:

```javascript
// Grid container — wraps cards automatically
grid = I(section, {
  type: "frame", name: "Product Grid",
  layout: "wrap",     // ⭐ CRITICAL — enables auto-wrapping            
  width: "fill_container",
  height: "hug_contents",          // grows with content
  gap: 12,                         // horizontal gap between cards
  counterAxisSpacing: 12           // vertical gap between wrapped rows
})

// Cards — fixed width, hug height
card = I(grid, {
  type: "frame", name: "Product Card",
  width: 165,                      // fixed width determines when to wrap
  height: "hug_contents",          // ⭐ NEVER fixed height on cards in grid
  layout: "vertical", gap: 8
})

// Card image — fill width
cardImg = I(card, { type: "frame", width: "fill_container", height: 165 })

```

**Key rules**:
- Grid: `layout: "wrap"` + `height: "hug_contents"` (mandatory)
- Cards: fixed `width` (controls column count) + `height: "hug_contents"` (adapts to content)
- Card images: `width: "fill_container"` (stretches to card width)
- Card width formula: `(available_width - gap × (columns - 1)) / columns`

```diff
❌ Fixed height cards in grid (clips or leaves whitespace):
   card = I(grid, { width: 165, height: 240 })

✅ Hug-height cards (adapts to varying content):
   card = I(grid, { width: 165, height: "hug_contents", layout: "vertical" })
```

## Text Nodes

- **Text has no color by default** — always set `fill` for visibility.
- For wrapping text, set `width: "fill_container"`(if parent has flexbox layout) or `width: (fixed number)`. Default `width: "hug_contents"` causes horizontal expansion.
- For single-line text, set `width: "hug_contents"` to resizing, make sure text would not overflow.
- `textAlignHorizontal` / `textAlignVertical` align text within the bounding box (only effective when `width: fill_container` or `"width: (fixed number)"`).
- `textAlignHorizontal` values: `LEFT`, `RIGHT`, `CENTER`. `textAlignVertical` values: `TOP`, `CENTER`, `BOTTOM`.
- Setting `textAlignHorizontal`/`textAlignVertical` does NOT change the text bounding box position — use flexbox layout for that.
- `lineHeight`: Set `lineHeight: "AUTO"` for automatic, or pass a **pixel integer** like `lineHeight: 36` for explicit spacing.
- Default font: `Inter`. Always specify `fontName` when creating text.

### Typography Code Example

```javascript
title=I("parent", {type: "text", name: "Page Title", content: "Welcome", fontSize: 32, fontName: {family: "Inter", style: "Bold"}, fill: "#18191C", textAlignHorizontal: "LEFT", width: "fill_container"})
```

## Components and Instances

> **Not in this file.** Load `func-rule/component-instance/SKILL.md` before creating/updating instances, setting `componentProperties`, or switching VARIANT / 激活态 / 变体. Variant switches are supported — do not refuse them as restricted.

## Working with Design Variables

> **Not in this file.** Load `func-rule/design-variables/SKILL.md` when binding/unbinding tokens (`$:Set:Var` / `$<id>`), calling `apply_variables`, or switching node `variableModes`.

## Working with Design Styles

> **Not in this file.** Load `func-rule/shared-styles/SKILL.md` when binding/unbinding `textStyleId` / `fillStyleId` / `strokeStyleId` / `effectStyleId`.

## Colors and Fills、Strokes

**IMPORTANT:** if fills/strokes type is `SOLID`, color only supports `r`, `g`, `b` fields.
**IMPORTANT:** if fills/strokes type is `GRADIENT_*`, color must provide `r`, `g`, `b` and `a` fields.

```javascript
// Simple fill using hex shorthand
U("nodeId", {fill: "#FF5733"})

// Detailed fill with opacity
U("nodeId", {fills: [{type: "SOLID", color: {r: 0.25, g: 0.48, b: 0.88}, opacity: 0.85, visible: true, blendMode: "NORMAL"}]})
// Detailed stroke
U("nodeId", {strokes: [{type: "SOLID", color: {r: 0.25, g: 0.48, b: 0.88}, opacity: 1, visible: true, blendMode: "NORMAL"}], strokeWeight: 5, strokeAlign: "INSIDE"})

// Linear gradient fill
U("nodeId", {fills: [{
  type: "GRADIENT_LINEAR",
  gradientStops: [
    {color: {r: 0.2, g: 0.4, b: 1.0, a: 1}, position: 0, boundVariables: {}},
    {color: {r: 1.0, g: 0.4, b: 0.3, a: 1}, position: 1, boundVariables: {}}
  ],
  gradientTransform: [[1, 0, 0], [0, 1, 0]],
  opacity: 1, visible: true, blendMode: "NORMAL"
}]})
```

Supported gradient types: `GRADIENT_LINEAR`, `GRADIENT_RADIAL`, `GRADIENT_ANGULAR`, `GRADIENT_DIAMOND`.

Note: `gradientStops` array must have at least two elements, and `boundVariables` can be empty but must be present.

## Tables

Strict hierarchy: **Table (frame) → Row (frame) → Cell (frame) → Content**

Each cell must be a frame wrapping content. Never put text directly in a row.

```javascript
// ✅ Correct
tableRow=I("tableId", {type: "frame", name: "Row", layout: "horizontal", width: "fill_container"})
cell1=I(tableRow, {type: "frame", name: "Cell", width: "fill_container"})
text1=I(cell1, {type: "text", name: "Name", content: "John", fill: "#18191C"})

// ❌ Wrong — text directly in row, missing cell frame
badRow=I("tableId", {type: "frame", layout: "horizontal"})
badText=I(badRow, {type: "text", content: "John"})
```

## Images

### Gradient Fills as Image Placeholders

Before Fill Real Images, use `GRADIENT_LINEAR` fills as visually appealing placeholders:
**IMPORTANT:** if fills/strokes type is `GRADIENT_*`, color must provide `r`, `g`, `b` and `a` fields.

```javascript
U("imageFrame", {fills: [{type: "GRADIENT_LINEAR",
  gradientStops: [
    {color: {r: 0.29, g: 0.73, b: 0.56, a: 1}, position: 0, boundVariables: {}},
    {color: {r: 0.16, g: 0.50, b: 0.73, a: 1}, position: 1, boundVariables: {}}
  ],
  gradientTransform: [[0.7, 0.7, 0], [-0.7, 0.7, 0.3]],
  opacity: 1, visible: true, blendMode: "NORMAL"}]})
```

Use different color schemes for different cards/sections to maintain visual distinction.

## Effects

Supported types: `DROP_SHADOW`, `INNER_SHADOW`, `LAYER_BLUR`, `BACKGROUND_BLUR`.

```javascript
// Drop shadow
U("cardId", {effects: [{type: "DROP_SHADOW", color: {r: 0, g: 0, b: 0, a: 0.3}, offset: {x: 0, y: 20}, radius: 40, spread: -8, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}}]})

// Inner shadow
U("cardId", {effects: [{type: "INNER_SHADOW", color: {r: 0, g: 0, b: 0, a: 0.3}, offset: {x: 0, y: 20}, radius: 40, spread: -8, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}}]})

// Layer blur
U("cardId", {effects: [{type: "LAYER_BLUR", radius: 20, visible: true, boundVariables: {}}]})

// Background blur
U("cardId", {effects: [{type: "BACKGROUND_BLUR", radius: 10, visible: true, boundVariables: {}}]})
```

Multi-layer shadow for realistic elevation:

```javascript
U("cardId", {effects: [
  {type: "DROP_SHADOW", color: {r: 0, g: 0, b: 0, a: 0.3}, offset: {x: 0, y: 20}, radius: 40, spread: -8, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}},
  {type: "DROP_SHADOW", color: {r: 0, g: 0, b: 0, a: 0.6}, offset: {x: 0, y: 8}, radius: 24, spread: -4, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}},
  {type: "DROP_SHADOW", color: {r: 0, g: 0, b: 0, a: 0.9}, offset: {x: 0, y: 4}, radius: 4, spread: 0, visible: true, blendMode: "NORMAL", showShadowBehindNode: false, boundVariables: {}}
]})
```

- Layer 1 (near): small offset, tight blur — edge definition
- Layer 2 (mid): medium offset, wide blur — depth cue
- Layer 3 (far): large offset, very wide blur — ambient glow
- If you need to create a frosted glass effect, set all `fills`'s `opacity` below 0.5.

## SVG Icons

- **Icons MUST be SVG nodes.** Never use icon fonts, emojis, Unicode geometric/dingbat glyphs, or single-letter text inside a circle as a substitute for an icon.
- **Putting an emoji / Unicode glyph into a `type: "text"` node's `content` is NOT a valid icon.** The text-with-emoji shortcut below is a recurring failure mode — recognize it and reject it before writing the op.

```javascript
// ❌ FORBIDDEN — emoji / glyph inside a text node masquerading as an icon
weatherIcon=I(weatherBadge, {type: "text", name: "Weather Icon", content: "☀️", fontSize: 14})
checkIcon=I(card, {type: "text", content: "✓", fontSize: 16})
arrowIcon=I(button, {type: "text", content: "▶", fontSize: 12})

// ✅ CORRECT — frame node with real SVG markup
weatherIcon=I(weatherBadge, {type: "frame", name: "Weather Icon", layout: "none", width: 24, height: 24,
  svg: "<svg viewBox=\"0 0 24 24\" fill=\"none\"><circle cx=\"12\" cy=\"12\" r=\"5\" fill=\"#FFB300\"/><path d=\"M12 2v3M12 19v3M2 12h3M19 12h3\" stroke=\"#FFB300\" stroke-width=\"2\" stroke-linecap=\"round\"/></svg>"})
```

- Use `type: "frame"` with `svg` property containing full SVG markup.
- When creating icon from frame, must set `layout: "none"`.
- Always `capture_screenshot()` after creating SVG icons to verify.

```javascript
icon=I("parent", {
  type: "frame",
  name: "Search Icon",
  svg: "<svg width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><circle cx=\"11\" cy=\"11\" r=\"7\" stroke=\"#333\" stroke-width=\"2\"/><path d=\"M16 16L20 20\" stroke=\"#333\" stroke-width=\"2\" stroke-linecap=\"round\"/></svg>",
  width: 24,
  height: 24
})
```


## Icon Components

- Always create icon as a component, then use `I(parentId, {type: "ref", ref: "iconId"})` to insert the icon instance.
- When creating icon from frame, must set `layout: "none"`.
- After creating icons, must run `capture_screenshot()` to verify the icon is correct.

## Frames

- Default Frame has a white background fill. To remove the background, set `fills: []`.
- Frames can be nested within other frames and serve as containers for child objects.
- When creating multiple screens, represent each one as a top-level frame.

```javascript
card=I("parent", {
  type: "frame",
  name: "Card",
  width: 320,
  height: 200,
  fill: "#FFFFFF",
  cornerRadius: 12,
  stroke: "#E0E0E0",
  strokeWeight: 1,
  effects: [{type: "DROP_SHADOW", color: {r: 0, g: 0, b: 0, a: 0.1}, offset: {x: 0, y: 2}, radius: 8, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}}],
  layout: "vertical",
  padding: 16,
  gap: 12
})
```

## Property Quick Reference

### Common Mistakes

| Wrong | Correct | Notes |
|---|---|---|
| `textColor: "#FFF"` | `fill: "#FFFFFF"` | Text color via `fill` |
| `backgroundColor: "#FFF"` | `fill: "#FFFFFF"` | Background via `fill` on frame |
| `color: "#FFF"` | `fill: "#FFFFFF"` | Always use `fill` |
| `fillColor: "#FFF"` | `fill: "#FFFFFF"` | Use `fill` |
| `borderRadius: 8` | `cornerRadius: 8` | Use `cornerRadius` |
| `fontWeight: "bold"` | `fontWeight: "700"` | Numeric strings only |
| `fontWeight: "semibold"` | `fontWeight: "600"` | Numeric strings only |
| `fontWeight: "medium"` | `fontWeight: "500"` | Numeric strings only |
| `alignItems: "center"` | `counterAxisAlignItems: "CENTER"` | Uppercase enum |
| `justifyContent: "center"` | `primaryAxisAlignItems: "CENTER"` | Uppercase enum |
| `verticalAlign: "center"` | `counterAxisAlignItems: "CENTER"` | Uppercase enum |

### Alignment

| Purpose | Property | Valid Values |
|---|---|---|
| Main axis | `primaryAxisAlignItems` | `"MIN"`, `"CENTER"`, `"MAX"`, `"SPACE_BETWEEN"`, `"SPACE_EVENLY"` |
| Cross axis | `counterAxisAlignItems` | `"MIN"`, `"CENTER"`, `"MAX"`, `"BASELINE"` |
| Cross axis content | `counterAxisAlignContent` | `"AUTO"`, `"SPACE_BETWEEN"` |

### Size Values

| Value | Behavior |
|---|---|
| Numeric (`400`) | Exact pixel size |
| `"fill_container"` | Stretch to fill parent |
| `"fill_container(200)"` | Fill with 200px minimum |
| `"hug_contents"` | Shrink-wrap to fit children |
| `"hug_contents(600)"` | Hug with 600px minimum |

### Font Weight

| Value | Style |
|---|---|
| `"100"` | Thin |
| `"200"` | Extra Light |
| `"300"` | Light |
| `"400"` | Regular (default) |
| `"500"` | Medium |
| `"600"` | Semi Bold |
| `"700"` | Bold |
| `"800"` | Extra Bold |
| `"900"` | Black |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Text invisible | Missing `fill` | Add `fill: "#000000"` |
| Text overflows | `width: hug_contents` | Set `width: "fill_container"` (or fixed width)|
| Instance text garbled | Font/resize issue in instance | Re-set `width`, `fontName` on **component** |
| Instance no background | `fills` empty | Explicitly set `fill` on instance |
| Child path not found | Wrong ID format | `batch_read` with `resolveInstances: true` for semicolon IDs |
| Content clipped | `clipsContent: true` + fixed height | Set `height: "hug_contents"` or increase |
| Shadows not visible | `visible: false` or `a: 0` | Set `visible: true`, alpha > 0 |
| Font different | Unavailable style | Use "Regular", "Medium", "Bold" for Inter |
| Children misaligned | Wrong axis prop | `counterAxisAlignItems: "CENTER"` for cross-axis |
| Children not spread | No distribution | `primaryAxisAlignItems: "SPACE_BETWEEN"` |

## General Best Practices

- If a property is not defined, treat it as 0 — do not hallucinate values.
- Exclude default property values unless overriding a non-default inside an instance.
- Avoid `width: 0` and `height: 0`.
- Keep color float values to 2 decimal places.
- Favor copying existing content + updating over generating from scratch.

- Always validate with **tiered validation** after design changes (see Post-Generation Validation Pattern below) — not every batch needs a full screenshot+layout check.
- Always need call `locate_available_space` tool before inserting a node on root page.
- If possible, first create reusable components that will be used as building blocks. Place these separately on the canvas.
- If possible, first create reusable variables that will make the design easier to change themes.
- Use `batch_read` by listing reusable nodes in a design system frame, when working with a design system or design kit frame, to understand what components are available.

## Post-Generation Validation Pattern

> **Guiding principle**: validation exists to catch real defects, not to re-inspect already-good work. Every extra `capture_screenshot` / `capture_layout` call costs a round-trip. Validate with the lightest tool that can catch the failure modes of the batch you just ran, and stop as soon as the design is acceptable.

### Tiered Validation (apply per batch_edit)

Pick the tier that matches what the batch changed. **Do not run full dual-verification after every batch.**

| Batch type | What it changed | Validation |
|---|---|---|
| **T1 — Structural scaffold** | New frames, layout mode, padding, hierarchy | `capture_layout(problemsOnly: true)` only — screenshot not useful yet |
| **T2 — Content fill** | Text content, token binding, component instance props | **Skip validation**; defer to the next style/phase batch |
| **T3 — Visual/style** | `fill`, typography, effects, cornerRadius, strokes | `capture_screenshot` only |
| **T4 — Section complete** | A whole logical section (hero, features, footer) is done | Run **both** `capture_screenshot` + `capture_layout(problemsOnly: true)` **once** |
| **T5 — Final page** | All sections merged | One final `capture_screenshot` of the full page |

Every `capture_screenshot` validation requires reading each returned image file. A saved path is not visual validation. Findings visible in the screenshot are tool evidence even when `capture_layout` is clean.

`capture_layout` reports large-empty-area warnings by default. Treat them as review candidates: confirm from the screenshot and page contract whether the space is intentional before fixing container size, padding, or missing content.

Rules of thumb:
- If two consecutive batches are both T2 or T3, validate **once at the end**, not after each.
- Prefer batching corrective fixes: accumulate issues and fix them in **one** `batch_edit`, then re-validate once.
- `capture_screenshot` for nodes > 2000px tall: screenshot sections, not the whole node.

### Convergence Threshold — When to Stop Iterating

Validation loops must **terminate**. Apply these stop conditions:

1. **Hard cap**: at most **2 fix iterations** per section. If a third pass is about to start, stop blind retries and record the remaining issue. Missing requested content, duplicated primary actions/navigation, unreadable data, empty modules, or wrong component semantics remain blocking: use a different implementation approach or report the result as incomplete; never present them as a successful delivery.
2. **Ignore cosmetic noise** from `capture_layout`:
   - Spacing deltas ≤ 4px
   - Sub-pixel misalignment (< 1px)
   - Non-critical overflow in decorative/background nodes
   - Problems on nodes outside the section currently being built
3. **No subjective re-polishing**: once a section matches the style guide and has no structural problems, **do not** run additional screenshots "to double-check" or to hunt for aesthetic improvements. Ship it.
4. **Use tool evidence**: fix structural findings from `capture_layout` and visible defects from the screenshot. Do not invent issues unsupported by either source, but never dismiss a visible semantic defect merely because layout is clean.

### Corrective Fix Protocol

When a tier's validation does surface real issues:
1. Accumulate **all** issues from the validation call.
2. Issue **one** corrective `batch_edit` that addresses them together.
3. Re-run **only the same tier's validation** (don't upgrade to full dual-verification just because you fixed something).
4. If still failing and you're at iteration 2 → stop, note the issue, proceed.

## ⛔ Forbidden Patterns

- **Emoji or Unicode pictographs anywhere in a `type: "text"` node's `content`** — not as an icon, not as a section-title prefix, not as a label decoration, not as a button suffix. Forbidden in every form, including:
  - Standalone: `content: "☀️"`, `content: "✓"`, `content: "▶"`
  - Prefix: `content: "🏝️ 热门"`, `content: "📸 旅行瞬间"`, `content: "👋 好友动态"`
  - Suffix: `content: "编辑 ✏️"`, `content: "查看更多 →"`
  - Mixed: any `content` string containing characters in U+2300–U+27BF, U+2600–U+27BF, or U+1F300–U+1FAFF.

  Visual symbols MUST be a separate `type: "frame"` + `svg` node; text nodes hold pure text only. If you want an icon next to a label, build a horizontal flex frame with `[svg-frame, text-node]` — never merge them into one string.
- `type: "icon_font"` / `iconFontName` / `iconFontFamily` — deprecated, no engine support.
- Single-letter text in a circle as a fake icon.

### Common Post-Verification Fixes

| Issue | Fix |
|-------|-----|
| Text invisible on sub-frame | Set `fills: []` on the sub-frame so parent bg shows through |
| Font style not found | Call `get_available_fonts` and update with exact style name |
| Cards overlapping | Check parent has `layout: "horizontal"` or `wrap` or `"vertical"` |
| Elements misaligned | Set `counterAxisAlignItems: "CENTER"` on parent |
