---
name: shared-styles
description: Bind/unbind shared styles via textStyleId/fillStyleId/strokeStyleId/effectStyleId (bare nodeId or Style:key,ver; never `$`)
disable-model-invocation: true
user-invocable: false
---

# Working with Shared Styles

Bind reusable shared styles (text / fill / stroke / effect) to nodes by GUID. The `<StyleId>` is the style nodeId.

| Location | template |
|---|---|
| Local | `xxxStyleId:<StyleId>` |
| Team library | `xxxStyleId:<StyleId>, libraryKey:<LibraryKey>` |

```javascript
title=I(parent, {type: "text", content: "Heading", textStyleId: "<StyleId>"})

card=I(parent, {type: "frame", fillStyleId: "<StyleId>"})
card=U("nodeId", {strokeStyleId: "<StyleId>"})

card=U("nodeId", {effectStyleId: "<StyleId>"})

libraryCard=I(parent, {type: "frame", fillStyleId: "366:20", libraryKey: "693499159567438"})
```

## Style Rules

- ID format: pass the bare style nodeId. Do NOT prepend `$` (that prefix is for variable references).
- `textStyleId` is TEXT-only. `fillStyleId` / `strokeStyleId` apply to any node with fills/strokes. `effectStyleId` applies to any node with effects.
- Style binding wins at render time over inline `fontName`/`fills`/`strokes`/`effects` — when binding a style, omit the matching literal property unless overriding for a single instance.
- For team-library styles, pass `styleId` and `libraryKey` from `search_styles`.
- To remove a style binding, set the field to `null`:

```javascript
U("nodeId", {textStyleId: null, fillStyleId: null, strokeStyleId: null, effectStyleId: null})
```
