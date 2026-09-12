---
name: design-variables
description: Bind/unbind design variables (tokens) on node props with `$:<Set>:<Name>` or `$<id>`; create via apply_variables; switch node variable modes via batch_edit variableModes
disable-model-invocation: true
user-invocable: false
---

# Working with Design Variables

Bind reusable design tokens to node properties. References have two independent dimensions: **location** (local or team library) and **addressing** (name or GUID), producing four canonical forms:

| Location | Name-based | GUID-based |
|---|---|---|
| Local | `$:<SetName>:<VariableName>` | `$<variableId>` |
| Team library | `$lib:<libraryKey>:<SetName>:<VariableName>` | `$lib:<libraryKey>:<setId>:<variableId>` |

Use the ids and names returned by `fetch_variables`. For team-library variables, call it with `enabledLibraryKey`. A reference must use either name-based or GUID-based addressing consistently; do not mix them. Prefer GUID-based references when names may drift.

Use `apply_variables` to create new ones. Variable types: `FLOAT`, `COLOR`, `BOOLEAN`, `STRING`.

```javascript
card=I(container, {type: "frame", width: "$:Primitives:card-width", cornerRadius: "$:Primitives:radius-lg", padding: "$:Primitives:spacing-md", fill: "$:Semantic:bg-color", visible: "$:Flags:show-card"})
title=I(card, {type: "text", content: "$:Content:app-title", fontSize: "$:Primitives:heading-size", fontFamily: "$:Primitives:body-font", fill: "$:Semantic:text-primary"})
card2=I(container, {type: "frame", fill: "$1:1", cornerRadius: "$1:2"})
libraryByName=I(container, {type: "frame", fill: "$lib:703421493701878:M3:Schemes/Primary", width: "$lib:693499159567438:Spacing:md"})
libraryByGuid=I(container, {type: "frame", fill: "$lib:693499159567438:12:5:12:8"})
```

## Supported Variable Binding Properties

**FLOAT** (Node) — `width`, `height`, `minWidth`, `maxWidth`, `minHeight`, `maxHeight`, `itemSpacing`, `counterAxisSpacing`, `paddingLeft`, `paddingRight`, `paddingTop`, `paddingBottom`, `padding` (binds all four sides), `cornerRadius`, `topLeftRadius`, `topRightRadius`, `bottomLeftRadius`, `bottomRightRadius`, `strokeWeight`, `strokeTopWeight`, `strokeRightWeight`, `strokeBottomWeight`, `strokeLeftWeight`, `opacity`, `gridRowGap`, `gridColumnGap`

**FLOAT** (Text) — `fontSize`, `letterSpacing`, `lineHeight`, `paragraphSpacing`, `paragraphIndent`

**STRING** — `content` (also accepts FLOAT, auto-stringified)

**BOOLEAN** — `visible`

**COLOR** — `fill`, `stroke` (shorthand for single solid paint), or `color: "$:Set:var"` inside `fills`/`strokes` arrays:

```javascript
// Shorthand single-color binding (preferred)
U("nodeId", {fill: "$:Semantic:bg-color", stroke: "$:Semantic:border-color"})

// Inside fills/strokes array (for multiple paints or gradient stops)
U("nodeId", {fills: [{type: "SOLID", color: "$:Semantic:surface-color"}]})
U("nodeId", {fills: [{type: "GRADIENT_LINEAR", gradientStops: [{color: "$:Brand:brand-start", position: 0}, {color: "$:Brand:brand-end", position: 1}], gradientTransform: [[1, 0, 0], [0, 1, 0]]}]})
```

## Variable Rules

- Team-library references import the variable set before binding.
- Variable set names and variable names must NOT contain `$` or `:` characters.
- Strings like `$99.99`, `$HOME`, `$(document)` are treated as plain text, not variable references.
- Type must match: FLOAT for number properties, COLOR for fill/stroke, BOOLEAN for visible, STRING for content/fontFamily.
- Variable references on unsupported properties (e.g., `x`, `y`, `rotation`) are skipped with a warning.
- `padding: "$:Set:var"` (or `padding: "$<variableId>"`) binds all four padding sides simultaneously.
- COLOR binding uses the variable's current color as fallback; if unavailable, a warning is reported.

## Unbinding Variables

To remove an existing variable binding from a property, set the property value to `null`:

```javascript
// Unbind opacity
U("nodeId", {opacity: null})

// Unbind all four padding sides at once
U("nodeId", {padding: null})

// Unbind specific fields
U("nodeId", {cornerRadius: null, strokeWeight: null, visible: null})
```

## Switch Variable Modes on Nodes

Variable sets can define multiple **modes** (e.g. `Light` / `Dark`). Binding a variable to a node property always points at the variable itself; which mode's value is resolved depends on the **mode override** on that node (or an ancestor). Switching mode is how you flip a theme / density / brand without rebinding every property.

### Agent API

Use `variableModes` in `U()` / `I()` (via `batch_edit`) to set or clear mode overrides on a node:

```javascript
// GUID-based — setId → modeId (ids from fetch_variables)
U("frameId", {variableModes: [{variableSetId: "222:2", modeId: "345:1"}, {variableSetId: "225:3", modeId: "612:1"}]})

// Team-library - setId + modeId + libraryKey
U("frameId", {variableModes: [{variableSetId: "412:2", modeId: "35:1", libraryKey: "680350674110336"}]})

// Clear override → Auto (inherit from parent / use the set's default mode)
U("frameId", {variableModes: [{variableSetId: "222:2", modeId: null}]})

```

**Important:** use the `variableSetId` / mode `id` (and `libraryKey` when present) returned in `availableVariableModes` from `fetch_variables({ nodeId })`. Mode id must belong to that set's `modes` list — do not invent ids.

### Workflow

1. Decide the target node:
   - Prefer the **page** or a **top-level frame** when switching an entire screen/theme.
   - Override on a subtree root only when part of the design should stay on another mode.
2. `fetch_variables({ nodeId })` — read `availableVariableModes[]` for each switchable set's `variableSetId` (and optional `libraryKey`) plus `modes: [{id, name}]`.
3. Apply with `U(nodeId, {variableModes: [...]})`.
4. Re-read / screenshot if needed — bound variables (`$:Set:Var`) keep the same bindings; resolved values change with the active mode.

### Mode Rules

- `variableModes` is an array of `{variableSetId, modeId, libraryKey?}` entries.
  - `variableSetId`: use `availableVariableModes[].variableSetId` from `fetch_variables({ nodeId })`.
  - `modeId`: use an id from that set's `modes` list; use `null` to clear the explicit override.
  - `libraryKey`: required for a team-library variable set (from `availableVariableModes[].libraryKey`); omit it for a local set.
- Use ids exactly as returned by `fetch_variables({ nodeId })`; names and invented ids are not valid mode references.
- Only variable sets returned for the target node are switchable. Unknown set/mode entries are skipped with a warning.
- Mode resolves **down the tree**: a child's explicit mode wins over an ancestor's; Auto means inherit.
- Switching mode does **not** change variable bindings on properties. Bindings stay as `$:Set:Var` / `$<id>`; only the resolved value changes.
- Prefer one mode switch on a common ancestor over repeating the same `variableModes` on every leaf.
