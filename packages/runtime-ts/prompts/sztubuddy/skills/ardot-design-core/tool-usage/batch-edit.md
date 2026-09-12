Execute multiple insert/copy/update/move/delete/image operations in a single call.

## Usage

- Keep each batch_edit call to **maximum 25 operations** for optimal performance.
- For larger designs, split work into multiple batch_edit calls by logical sections (e.g., screen structure first, then sidebar content, then main content).
- Avoid creating large operation objects like an insert with multiple descendants. Prefer breaking it down into many separate operations instead.
- If one of the operations fails, all previously executed operations in that block will be rolled back.
- Important: always create new binding names for every operation list, DO NOT reuse binding names across operation lists.
- A list of potential issues will be returned in the response message. Try to fix them in the next batch_edit call.

### Key Points

- Every Insert (I), Copy (C) operation MUST have a binding name. To reference a parent node in later operations, use the binding name from an earlier Insert, Copy operation in the same operation list.
- Not all bindings need to be used as parents later - it's okay to have "unused" bindings. The requirement exists to enforce deliberate structure.
- Bindings only work within the same batch_edit call for parent references
- Operations execute sequentially; on error, all operations in the list will be rolled back.

### Operation list format

You can create a list of operations in the following syntax:

- Every single operation must follow the Javascript syntax described below.
- ONLY these operation functions are supported.
- Every single operation line must be a single operation call with a possible binding assignment and nothing else.
- For node data, always follow the .ardot schema.
- This parent node will be used for the operations inserted/copied/moved. For these operations defining a parent is REQUIRED.
- The Page Node does not have a binding name, always use the page node's ID as the parent to Insert in page.

### Working with Existing Frames

- Use the frame's ID directly as the parent: `existingFrameId`
- If you update a frame's layout properties, insert children INTO that same frame using its ID

### Using bindings for paths and node ids

- You can use a binding variable name instead of an inline string an operation call
- If you want to combine it with some other binding or a string use the "+" operator
- IMPORTANT: DO NOT try to Update (U) a node's descendant that you just copied (C), since copying will recreate the descendant nodes and it will assign new IDs to those children nodes.

For example:

``` javascript
foo=I("pageId", { type: "ref", ref: "caSd2fv" })
U(foo+"Csawf3", {content: "+240%"})
D(foo)
```

Example - Adding content to existing frame "MmNEt":

``` javascript
U("MmNEt", {layout: "horizontal", gap: 16})
sidebar=I("MmNEt", {type: "ref", ref: "JRlf7", width: 240})
content=I("MmNEt", {type: "frame", layout: "vertical"})
header=C("A2sa3f", content, {width: "fill_container", height: "fill_container"})
```

### Response

A list of created or updated nodes and their updated properties.

### Insert (I)

Definition: insertedNodeId=I(parent: string, nodeData: Schema.Child)

- Important: "id"s are always created automatically for nodes, never create "id" properties in new node data.
- To insert an SVG node, use `type: "frame"` with a `svg` property containing the SVG string. The SVG will be parsed and converted into a FrameNode with vector children. You can set additional properties like `name`, `x`, `y`, `width`, `height` alongside `svg`.
- An insert can only be a single node, if you want to add children to it, use bindings and do it in a new Inert (I) operation.
- When working with components (reusable: true), insert their instances as refs with their properties overridden. If you want to override properties of subcomponents use subsequent Update (U) operations.
- Returns the inserted node ID as string
- **IMPORTANT:** Every created node must be actively assigned a meaningful `name`.
- **IMPORTANT:** Never insert nodes into an instance node or any instance node children, because they are virtual nodes and cannot be add new nodes.

### Copy (C)

Definition: copiedNodeId=C(path: string, parent: string, copyNodeData: Schema.Child & { positionPadding?: number; positionDirection?: string })

- When copying a node and modifying its descendants, you MUST use the "descendants" property in the Copy operation itself. DO NOT use separate Update operations for descendants of copied nodes, as this will fail due to ID mismatches. The copied node and its descendants receive new IDs, so Update operations referencing the original descendant IDs will fail.
- "path": The ID of the existing node to copy. If you want to customize some properties of the copied node, just add them next to the 'path' property. If you want to customize nested nodes _under_ the copied one, use the same kind of 'descendants' map that 'ref' nodes use!
- "descendants": Optional, used for components. An object which keys are node IDs or paths to descendant objects inside the component used to customize the properties of descendant objects.
- Example of correct usage: 'label1=C("NKYzH", container, {"descendants": {"ZopUS;jEYMs": { "content": "First Name" }}})'
- "positionPadding": The minimum padding distance from other element when positioning if needed.
- "positionDirection": The direction to search for empty space relative to the node, to position the copied node if needed. Possible values are: "top", "right", "bottom", "left"
- Copying a reusable node creates a connected instance (a 'ref' node).
- Returns the copied node ID as string

### Update (U)

Definition: U(path: string, updateData: Schema.Child)

- Update the properties of existing nodes, without listing their children.
- Use this operation to create small incremental updates to the properties of existing nodes.
- This operation CANNOT change the 'id', 'type' or 'ref' properties of any node!
- "path": The valid ID of the existing node to update (DO NOT use bindings in "path"), or if you want to update a nested node inside a instance, use the ID of the nested node must be prefixed with the ID of the instance and a (;). E.g. consider this component:
{
	"id": "button",
	"type": "frame",
	"reusable": true,
	"children": [{ "id": "container", "type": "frame", "children": [{"id": "label", "type": "text", "content": "Button text"}] }]
}
And then an instance of this component like this: {"id": "submit-button", "type": "ref", "ref": "button"}
The label text of 'submit-button' can be changed by passing the following as the "nodes" parameter:

``` javascript
U("submit-button;label", {content: "Submit"})
```

This slash-separated instance ID scheme works for any number of nesting levels, not just two.

- "updateData": The node data to update

### Move (M)

Definition: M(nodeId: string, parent: string | undefined, index?: number)

- Move a nodes to a different location in the node tree in a .ardot file.
- "path": The id of the moved node. ALWAYS use a valid node id, NOT a path or binding.
- "parent": Optional parent node Id or binding
- "index": Optional new position of the moved node among its siblings. If omitted, the node is placed at the end.

### Delete (D)

Definition: D(nodeId: string)

- Delete a node from a .ardot file.
- "nodeId": The ID of the node to delete. ALWAYS use a valid node id, NOT a path or binding.

### Generate Image (G)

Definition: G(nodeId: string, type: "ai" | "placeholder", prompt: string)

- IMPORTANT: There is NO "image" node type! Images are applied as FILLS to frame/rectangle nodes.
- Do not generate random URLs for image fills, always use the G operation to get an image from an AI service.
- To display an image: first Insert a frame or rectangle, then use G to apply the image as a fill.
- "nodeId": The ID of the frame/rectangle node to apply the image fill to. Can be a valid node ID or a binding name (e.g., "myFrame") created earlier in this operation list.
- "type": One of:
  - `"ai"` — AI-generated images related to the content (uses `prompt`).
  - `"placeholder"` — a gray placeholder image with a centered text label (from `prompt`) is applied as the fill. Use for fast drafts/wireframes, or when image generation is unavailable/undesired.
- "prompt":
  - For `"ai"`: a full descriptive prompt of the image to generate.
  - For `"placeholder"`: a **short label** (≤ 20 chars, ~2–4 words) shown on the placeholder, e.g. `"Hero image"`, `"User avatar"`. NOT a full AI prompt — long text overflows and looks broken. The label MUST be written in the same language as the user, e.g. use Chinese labels like `"封面图"`, `"用户头像"` when the user speaks Chinese.

Examples:
- AI-generated image on existing node:

``` javascript
G("logo-frame", "ai", "minimalist coffee shop logo, flat design")
```

- Placeholder image (drafts/wireframes; pass a SHORT label ≤ 20 chars):

``` javascript
avatar=I("parentId", {type: "frame", name: "Avatar", width: 120, height: 120})
G(avatar, "placeholder", "User avatar")
```

### Examples

**Example: Dashboard layout structure (8 ops)**

Add Sidebar and main content structure to a dashboard frame. Prefer adding components directly into an existing frame.

``` javascript
sidebar=I("29c0s", {type: "ref", ref: "JRlf7", x: 0, y: 0, width: 240, height: "fill_container"})
mainContent=I("29c0s", {type: "frame", layout: "vertical", gap: 24, padding: 32})
stats=I(mainContent, {type: "frame", layout: "vertical", gap: 16})
card1=I(stats, {type: "ref", ref: "QMBKc", width: "fill_container", height: "hug_contents"})
card2=I(stats, {type: "ref", ref: "QMBKc", width: "fill_container", height: "hug_contents"})
card3=I(stats, {type: "ref", ref: "QMBKc", width: "fill_container", height: "hug_contents"})
U("FVge3x;vdS2egl", {width: "fill_container", height: "fill_container"})
U("FVge3x;gDsgE6S", {content: "Submit"})
```

**Example: Form inputs section (8 ops)**

Add form inputs with labels to an existing content area.

``` javascript
label1=I("mainContent", {type: "ref", ref: "NKYzH"})
U(label1+"ZopUS;jEYMs", {content: "First Name"})
input1=I("mainContent", {type: "ref", ref: "FmgD2", width: "fill_container"})
U(input1+"CvD2R", {content: "First Name"})
input2=I("mainContent", {type: "ref", ref: "FmgD2", width: "fill_container"})
U(input2+"CvD2R", {content: "Last Name"})
U(contact+"oknii", {content: "Full Name"})
```

This example inserts a component directly into an existing frame.

``` javascript
sidebar=I("d3902", {type: "ref", ref: "JRlf7", x: 0, y: 0, width: 240, height: "fill_container"})
```

Copying a non-reusable frame (e.g., duplicating a screen). This copies the dashboard created above and tweaks it as another variation:

``` javascript
dashboardV2=C("Xk9f2", "pageId", {name: "Dashboard V2", positionDirection: "right", positionPadding: 100})
D(dashboardV2+"sidebarId")
U(dashboardV2+"statsId;card1Id", {fill: "#E8F5E9"})
U(dashboardV2+"statsId;card2Id", {fill: "#FFF3E0"})
```

**Important:** When creating icons, prefer SVG node over icon fonts.

**Important:** Inserting an SVG node. Use `type: "frame"` with a `svg` property containing the full SVG markup:

``` javascript
triangle=I("parentId", {type: "frame", svg: "<svg width=\"261\" height=\"109\" viewBox=\"0 0 261 109\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M1 108L84 1L259 97L1 108Z\" stroke=\"black\"/></svg>", name: "Triangle Shape", x: 100, y: 50})
```

When setting fill colors, keep color values to 2 decimal places to avoid excessively long floating-point numbers.

``` javascript
U("nodeId", {fills: [{type: "SOLID", color: {r: 0.25, g: 0.48, b: 0.88}, opacity: 0.85, visible: true, blendMode: "NORMAL"}]})
```

Applying a gradient fill to an existing node. Use `fills` with `type: "GRADIENT_LINEAR"`, `gradientStops` (array of color stops), and `gradientTransform` (2x3 matrix), note that `gradientStops` array should have at least two elements, and `boundVariables` can be empty but must be present:

| gradientTransform Direction | Matrix |
|-----------------------------|--------|
| left → right | [[1, 0, 0], [0, 1, 0]] |
| right → left | [[-1, 0, 1], [0, -1, 1]] |
| top → bottom | [[0, 1, 0], [-1, 0, 1]] |
| bottom → top | [[0, -1, 1], [1, 0, 0]] |
| 45° (ur → ll) | [[1, 1, 0], [-1, 1, 0.5]] |

``` javascript
U("nodeId", {fills: [{type: "GRADIENT_LINEAR", gradientStops: [{color: {r: 0.2, g: 0.4, b: 1.0, a: 1}, position: 0, boundVariables: {}}, {color: {r: 0.8, g: 0.2, b: 0.8, a: 1}, position: 0.5, boundVariables: {}}, {color: {r: 1.0, g: 0.4, b: 0.3, a: 1}, position: 1, boundVariables: {}}], gradientTransform: [[1, 0, 0], [0, 1, 0]], opacity: 1, visible: true, blendMode: "NORMAL"}]})
```

Supported gradient types: `GRADIENT_LINEAR`, `GRADIENT_RADIAL`, `GRADIENT_ANGULAR`, `GRADIENT_DIAMOND`.

**Example: Fixing layout alignment issues (3 ops)**

Fix a search bar where children are top-aligned instead of vertically centered, and distribute children to opposite ends (text on the left, button on the right). Use `counterAxisAlignItems: "CENTER"` for cross-axis centering, `primaryAxisAlignItems: "SPACE_BETWEEN"` for distributing children to both ends, and `layoutGrow: 1` to make a child fill the remaining space along the primary axis.

``` javascript
U("searchBar", {counterAxisAlignItems: "CENTER", primaryAxisAlignItems: "SPACE_BETWEEN"})
U("searchText", {layoutGrow: 1})
U("searchButton", {primaryAxisAlignItems: "CENTER", counterAxisAlignItems: "CENTER"})
```

**Example: Fixing text style inside a button (1 op)**

Fix button text color and size to ensure readability against the button background. Use `fills` to set text color and `fontSize` to adjust size.

``` javascript
U("buttonLabel", {fills: [{type: "SOLID", color: {r: 1, g: 1, b: 1}, opacity: 1, visible: true, blendMode: "NORMAL"}], fontSize: 14, fontName: {family: "Sarasa Gothic SC", style: "Bold"}})
```

## Common Property Mistakes — DO NOT USE These Invalid Properties

The following properties are **NOT supported** and will cause errors or be silently ignored. Always use the correct property name listed below.

| ❌ WRONG (Do NOT use) | ✅ CORRECT (Use this instead) | Notes |
|---|---|---|
| `textColor: "#FFF"` | `fill: "#FFFFFF"` | Text color is set via `fill` (a hex string), which maps to `fills` internally |
| `verticalAlign: "center"` | `counterAxisAlignItems: "CENTER"` | Use uppercase enum values for alignment |
| `alignItems: "center"` | `counterAxisAlignItems: "CENTER"` | `alignItems` is NOT a valid property |
| `justifyContent: "center"` | `primaryAxisAlignItems: "CENTER"` | `justifyContent` is NOT a valid property |
| `fontWeight: "bold"` | `fontWeight: "700"` | Use numeric strings: `"100"` to `"900"` |
| `fontWeight: "semibold"` | `fontWeight: "600"` | Maps to `"Semi Bold"` font style |
| `fontWeight: "medium"` | `fontWeight: "500"` | Maps to `"Medium"` font style |
| `fillColor: "#FFF"` | `fill: "#FFFFFF"` | Use `fill` for both text and shape colors |
| `backgroundColor: "#FFF"` | `fill: "#FFFFFF"` | Background color is just `fill` on a frame |
| `borderRadius: 8` | `cornerRadius: 8` | Use `cornerRadius` |
| `color: "#FFF"` | `fill: "#FFFFFF"` | Always use `fill` for colors |

### Font weight reference

Use **numeric strings** for `fontWeight`:

| Value | Font Style |
|---|---|
| `"100"` | Thin |
| `"200"` | Extra Light |
| `"300"` | Light |
| `"400"` | Regular |
| `"500"` | Medium |
| `"600"` | Semi Bold |
| `"700"` | Bold |
| `"800"` | Extra Bold |
| `"900"` | Black |

Default use `fontWeight: "400"`

### Font family reference

When creating a text node, you must specify the `fontName`, such as:

``` javascript
txt=I("nodeId", {type: "text", content: "...", fontSize: 16, fill: "#18191C", fontName: {family: "Inter", style: "Regular"}})
```

In general, you should use the font family and style that match your design system.
But if you want to use a specific font, you can specify it in the `fontName` property.
When not specified, use `Inter`.

**Important:** After creating text nodes, the system validates whether the fonts used are available. If a font is not available, you will see it in `potentialIssues`. To fix it:
1. Call `get_available_fonts` with the font family name as `keyword` (e.g., keyword: "Inter") to find its exact available styles
2. Pick an exact family + style match from the result
3. Use U() to update the text node's fontName with the correct font

Do NOT guess font style names — always use the exact strings from `get_available_fonts`.

### Alignment property reference

For frames with `layout: "horizontal"`, `layout: "vertical"` or `layout: "wrap"`:

> `primaryAxisAlignItems`, `counterAxisAlignItems` and `counterAxisAlignContent` will only work when the node has layout not `"NONE"`

| Purpose | Property | Valid Values |
|---|---|---|
| Main axis alignment | `primaryAxisAlignItems` | `"MIN"`, `"CENTER"`, `"MAX"`, `"SPACE_BETWEEN"`, `"SPACE_EVENLY"` |
| Cross axis alignment | `counterAxisAlignItems` | `"MIN"`, `"CENTER"`, `"MAX"`, `"BASELINE"` |
| Cross axis content (wrap) | `counterAxisAlignContent` | `"AUTO"`, `"SPACE_BETWEEN"` |

### Size property values

- **Numeric values**: `width: 400`, `height: 300` — sets exact pixel size
- **`"fill_container"`**: makes the node stretch to fill the parent's available space along that axis (requires parent to have layout)
- **`"fill_container(200)"`**: same as above, but with a minimum size of 200px
- **`"hug_contents"`**: makes the node shrink-wrap to fit its children

### Text color

Text nodes have **no visible color by default**. You MUST set the `fill` property:

``` javascript
title=I(parent, {type: "text", content: "Hello", fontSize: 16, fill: "#18191C"})
```

## Working with Component Instances

When you insert a component instance and want to modify its descendants:

1. **Update properties** → Use U() with the instance path:
``` javascript
card=I(body, {type: "ref", ref: "CardComp"})
U(card+"titleTextId", {content: "New Title"})
```

2. **Add new children** → Use I() on regular frames or Pages root:

``` javascript
container=I(body, {type: "frame", layout: "vertical"})
item=I(container, {type: "text", content: "New item"})
```

3. **Swap Instances** → Use U() with instance paths:

- it is also fit to swap nested instances use the `mainComponent` property.

``` javascript
card=I(CardRaw, {type: "ref", ref: "4:5"})
U(card+"2:3", {mainComponent: "1:8"})
```
