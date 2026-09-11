---
name: component-instance
description: "Create/update component instances; set componentProperties; switch VARIANT / 变体 via variantOptions. Triggers: instance, COMPONENT_SET, variant, 变体, componentProperties."
disable-model-invocation: true
user-invocable: false
---

# Components and Instances

- `COMPONENT` or `COMPONENT_SET` nodes are reusable (symbols).
- Insert instances with `type: "ref"` pointing to component/componentSet ID.
- For Component/ComponentSet: call `batch_read` with the ID to get `componentPropertyDefinitions`, then `batch_edit` to update instance properties.
- **Instance overrides**:
  - Root properties: set directly on the `ref` object
  - Descendant properties: use `descendants` map — `{descendants: {"childId": {content: "New"}}}`
  - Nested instances: slash-separated paths — `instanceId/nestedInstanceId/childId`
  - Replace subtree: include `type` in descendant override
  - "Delete" descendant: override `visible: false`
- When using `descendants`, paths can access multi-level descendant nodes — use paths in `descendants` keys, DO NOT create multiple levels of `descendants` objects.
- **Prefer updating the component** over individual instances for shared changes.
- ID formats: rendered tree uses **semicolons** (`instanceId;childId`), batch_edit uses **binding + nodeID** (`card+"childId"`). Fall back to semicolon ID if binding fails.
- Reuse existing components instead of creating duplicates.
- Instead of duplicating the same component multiple times with small tweaks, try to make them more generic so instances can reuse in more places.
- Cannot reference components across files — copy them over.
- Place reusable components on the side, next to the main design.
- Overrides are applied only to the overridden object — changes will NOT be inherited to all children.
- When parsing designs, treat "component" broadly — some are formal symbols, others are ad-hoc groupings visually behaving like components (sometimes prefixed "component/").

## Composition Contract

Before inserting a component, inspect its root sizing, exposed properties, visible controls, and nested instances. A component is reusable only when its semantics fit the role in this screen.

- **No duplicate affordances**: inspect composed components for built-in status bars, back buttons, search controls, titles, close actions, tabs, or bottom navigation before adding siblings with the same role. Keep exactly one primary affordance per action unless the user explicitly asks for both. "It is part of the native component" does not justify two back buttons or two status bars.
- **Give every repeated and nested instance distinct, scenario-derived text and icons**: update the text and icon slots within each relevant nested instance to reflect its real purpose and never keeps a component default. For menu rows, tabs, list rows, table columns, and cards, replace generic labels such as "菜单" or "默认选项", placeholder sequences, and repeated default or empty-box icons with a coherent set inferred from the page scenario; otherwise, it is a generation defect.
  - **Operations**: inspect nested descendants with `batch_read` using sufficient `readDepth` and `properties: ["mainComponent"]`. Override text through its TEXT component property or `U(instance+"childId", {content: "..."})`, and swap icons through `INSTANCE_SWAP` or `U(path, {mainComponent: "matchingIconId"})`.
- **Semantic fit over coverage**: do not instance a Table, Picker, Card, or other component merely because it was returned by search. Use it only when its interaction and content model match the requested module.
- **Preserve composite structure**: reuse the smallest complete component root; never use internal rows, columns, cells, items, or slots as standalone modules. Tables/DataGrids need headers, at least two columns, and data rows; otherwise use a list or fallback.
- **Adaptive sizing**: use `fill_container` on parent-driven axes and `hug_contents` on content-driven axes. Preserve verified intrinsic/fixed variants, and update relevant nested wrappers when their fixed sizing causes clipping or artificial gaps.

Use `descendants` property to override the child nodes inside the component.
``` javascript
butt=I("86:1", {type:"ref", ref: "85:67", descendants: { "85:68": { content: "Google"}, "85:69": { content: "$34.56"}}})
```

Or use `U()` to update the instance child nodes by combining the instance ID and the child node ID.
``` javascript
butt=I("86:1", {type:"ref", ref: "85:67"})
U(butt+"85:68", { content: "TECH"})
```

For an already created instance, if you want to update its source component, you can use `U(instance, {mainComponent: "newComponentId"})`, including nested instances which can also be changed in the same way.
**Swap Instance**:
``` javascript
butt=I("86:1", {type:"ref", ref: "85:67"})
U(butt, {mainComponent: "85:68"})
```

## Component Property Definitions

Use `componentPropertyDefinitions` in U() or I() to add, edit, or delete component properties on a Component or ComponentSet node. Pass an array of action objects:

**add** — Add a new property. Supports `BOOLEAN`, `TEXT`, `INSTANCE_SWAP`, and `VARIANT` types.
> `VARIANT` is only supported for nodes of type `COMPONENT_SET`.

```javascript
U("componentId", {componentPropertyDefinitions: [{action: "add", name: "Show Icon", type: "BOOLEAN", defaultValue: true}, {action: "add", name: "Label", type: "TEXT", defaultValue: "Button"}, {action: "add", name: "Size", type: "VARIANT", defaultValue: "Medium"}, {action: "add", name: "Icon", type: "INSTANCE_SWAP", defaultValue: "", options: {preferredValues: [{type: "COMPONENT", key: "iconCompKey"}]}}]})
```

The response `returnInfo` contains the added property IDs.

**edit** — Modify an existing property's name, default value, or preferred values.
- `name` is supported for all property types
- `defaultValue` is supported for `BOOLEAN`, `TEXT`, and `INSTANCE_SWAP`, but **NOT** for `VARIANT`
- `preferredValues` is only supported for `INSTANCE_SWAP`

```javascript
U("componentId", {componentPropertyDefinitions: [
  {action: "edit", name: "Label", newValue: {defaultValue: "Submit"}},
  {action: "edit", name: "Size", newValue: {name: "Variant"}},
  {action: "edit", name: "Show Icon", newValue: {name: "Has Icon", defaultValue: false}}
]})
```

**delete** — Remove an existing property. Only supports `BOOLEAN`, `TEXT`, and `INSTANCE_SWAP`. Cannot delete `VARIANT` properties.

```javascript
U("componentId", {componentPropertyDefinitions: [
  {action: "delete", name: "Show Icon"},
  {action: "delete", name: "Label"}
]})
```

## Bind Component Properties to Nodes

Use `componentPropertyReferences` in U() or I() to bind component properties to child node properties:

- `visible` — Reference to a boolean property controlling visibility.
- `characters` — Reference to a text property controlling text content.
- `mainComponent` — Reference to an instance swap property controlling the main component of an instance node.

**Important:** Use the property name defined in `componentPropertyDefinitions`. Before binding, ensure the property exists and the binding node is a child of the component.

```javascript
component=I("223:1",{type:"component", name: "component", layout: "horizontal", width: "hug_contents", height: "hug_contents", padding: 20, gap: 20, primaryAxisAlignItems: "CENTER", counterAxisAlignItems: "CENTER",componentPropertyDefinitions: [{action: "add", name: "Show Icon", type: "BOOLEAN", defaultValue: true}, {action: "add", name: "Label", type: "TEXT", defaultValue: "Button"}, {action: "add", name: "Icon", type: "INSTANCE_SWAP", defaultValue: "228:19"}]})
icon=I(component,{type:"ref", ref: "228:19", componentPropertyReferences: {visible: "Show Icon", mainComponent: "Icon"}})
text=I(component,{type:"text", text: "Text", fontSize: 24, componentPropertyReferences: {characters: "Label"}})
```

## Update Component Properties on Instance

**Important:** use the property name which is defined in `componentPropertyDefinitions` to set new value.

already exist three component nodes: `3:5` and `3:7`, and `3:11`, `3:11` has three component properties: Boolean Property: `Show Icon#252:1`, Text Property: `Label#252:2` and Instance Swap Property: `Icon#252:3`.

For a remote team-library component, add `libraryKey` to the `ref` node. Use the component's source node id (`assetId` from `component_search`) as `ref`, and the library source file id as `libraryKey`.

``` javascript
item1=I("35:2", {type: "ref", ref: "3:11", componentProperties: {"Show Icon#252:1": true, "Label#252:2": "Text1"}})
item2=I("35:2", {type: "ref", ref: "3:11"})
U(item2, {componentProperties: {"Show Icon#252:1": false, "Label#252:2": "Text2"}})
item3=I("35:2", {type: "ref", ref: "3:11", componentProperties: {"Show Icon#252:1": true, "Label#252:2": "Text3", "Icon#252:3": "3:7"}})
item4=I("35:2", {type: "ref", ref: "366:12", libraryKey: "693499159567438", componentProperties: {"Show Icon#252:1": true, "Label#252:2": "Remote"}})
```

## Update Variant Properties on Instance

**Important:** use the property name which is defined in `componentPropertyDefinitions` to set new value.
**Important:** use the property value which is provided in `variantOptions` to switch variant.

already exist a componentSet nodes: `55:2`, has three Variant properties: 
``` json
{"Type": {"type": "VARIANT","defaultValue": "Circle","variantOptions": ["Circle", "Rectangle"]},
"Size": {"type": "VARIANT", "defaultValue": "small", "variantOptions": ["big", "small"]},
"Color": {"type": "VARIANT", "defaultValue": "blue", "variantOptions": ["red", "blue"]}}
```

only use provided `variantOptions` to switch variant.

``` javascript
item1=I("45:2", {type: "ref", ref: "55:2", componentProperties: {"Type": "Rectangle", "Size": "small"}})
item2=I("45:2", {type: "ref", ref: "55:2", componentProperties: {"Type": "Circle", "Size": "small", "Color": "blue"}})
U(item2, {componentProperties: {"Show Icon": false, "Label": "Text2"}})
item3=I("45:2", {type: "ref", ref: "55:2", componentProperties: {"Type": "Rectangle", "Size": "big", "Color": "red"}})
```

# Make Sure Update Instance completely

**Important:** use the property name which is defined in `mainComponent:{componentPropertyDefinitions: ...}` to set new value.

## Customize a Complex Instance

Use task requirements or the asset mapping, when available, to identify nested content, state, icon, or sizing slots that require overrides. Reuse each source component's property map across its instances; do not recursively inspect every leaf by default.

**Workflow:**

1. Read the source component with the minimum depth needed to get its property definitions:
   ```javascript
   batch_read(nodeIds: ["instanceId"], readDepth: 2, resolveInstances: true, properties: ["mainComponent"])
   ```
2. Update mapped properties with `U()` using names from `mainComponent.componentPropertyDefinitions`:
   ```javascript
   U("instanceId", {componentProperties: {"Label#252:2": "New Text", "Show Icon#252:1": true}})
   ```
3. If a mapped slot remains unresolved, read only that subtree more deeply, up to `readDepth: 5`:
   ```javascript
   batch_read(nodeIds: ["nestedInstanceId"], readDepth: 3, resolveInstances: true, properties: ["mainComponent"])
   ```
4. Stop once all required mapped slots are resolved. Report unresolved optional or inaccessible slots rather than expanding into an unbounded read loop.

## Override Child Text Layers in (Nested) Instances

An instance's content may live in child TEXT layers, including nested instances. Override required mapped content with scenario-appropriate values. Identity and state fields should distinguish repeated records; shared actions, units, and common chrome may repeat.

```javascript
// Override mapped child text; common actions may intentionally repeat.
U("nestInstanceId1", {componentProperties: {"Label#..": "..."}})
U("nestInstanceId2", {componentProperties: {"Label#..": "..."}})

// When the text is a plain child text node rather than a TEXT component property, set its content directly:
U("nestInstanceId3/textChildId", {content: "..."})
```

## Hide Optional Children

Use the component's variant or BOOLEAN property when available. Otherwise, hide a descendant with `visible: false` when the task contract marks that content optional or the scenario does not use it. Do not invent data merely to keep an optional slot visible.

```javascript
U(instance+"childId", {visible: false})
```

or via `descendants` when inserting:

```javascript
I("86:1", {type: "ref", ref: "85:67", descendants: {"childId": {visible: false}}})
```
