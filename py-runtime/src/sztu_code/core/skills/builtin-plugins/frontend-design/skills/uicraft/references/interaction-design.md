---
name: Interaction Design
description: The eight states of an interactive element, sizing of click and touch targets, keyboard traversal, focus handling, and patterns for gestures.
---

## Contents

- [The Eight States Every Control Needs](#the-eight-states-every-control-needs)
- [Focus Rings Done Properly](#focus-rings-done-properly)
- [Form Details People Miss](#form-details-people-miss)
- [Communicating Work In Progress](#communicating-work-in-progress)
- [Modals With Inert And Dialog](#modals-with-inert-and-dialog)
- [Native Popovers](#native-popovers)
- [Placing Dropdowns And Overlays](#placing-dropdowns-and-overlays)
- [Undo Beats Confirmation](#undo-beats-confirmation)
- [Keyboard Movement Within Components](#keyboard-movement-within-components)
- [Making Gestures Discoverable](#making-gestures-discoverable)


# Designing Interaction

## The Eight States Every Control Needs

Design all eight before calling an interactive element finished:

| State | Triggered by | How it should read |
|-------|--------------|--------------------|
| **Default** | Nothing happening | The base styling |
| **Hover** | A pointer sits over it — never touch | A slight lift and a shift in color |
| **Focus** | Focus arrives from the keyboard or from code | A ring you can actually see (covered next) |
| **Active** | The press is happening now | Pushed in and darkened |
| **Disabled** | The control is off | Dimmed opacity, pointer events gone |
| **Loading** | Work is underway | A spinner or a skeleton |
| **Error** | The value is invalid | Red border plus an icon and a message |
| **Success** | The action landed | A green check and confirmation |

**Where teams slip**: styling hover but not focus, or focus but not hover. The two are not interchangeable — someone driving the UI from the keyboard will never trigger a hover state.

## Focus Rings Done Properly

Stripping `outline: none` and putting nothing back breaks accessibility, so never do it. Let `:focus-visible` limit the ring to keyboard interaction instead:

```css
/* Pointer and touch presses get no ring */
.chip:focus {
  outline: none;
}

/* Keyboard focus gets a ring */
.chip:focus-visible {
  outline: 2px solid var(--ring-color);
  outline-offset: 2px;
}
```

A ring that works has four properties:
- at least 3:1 contrast against whatever sits next to it
- a stroke of 2-3px
- placement outside the element via an offset, not tucked within its bounds
- the same treatment on every interactive element in the product

## Form Details People Miss

A placeholder cannot stand in for a label, because it vanishes the moment someone types — give every field a real, visible `<label>`. Run validation when the field loses focus rather than on each keystroke; password strength meters are the reasonable exception. Error text belongs **underneath** the field it describes, wired to the input through `aria-describedby`.

## Communicating Work In Progress

**Optimistic updates** paint the success state right away and roll back if the request fails. Reserve them for cheap, reversible interactions — likes and follows qualify; payments and deletions do not.

**Prefer skeletons over spinners.** A skeleton sketches the shape of the content that is about to arrive, which reads as faster than an anonymous spinner.

## Modals With Inert And Dialog

Trapping focus inside a modal once demanded fiddly JavaScript. The `inert` attribute replaces all of it:

```html
<!-- While the sheet is open -->
<main inert>
  <!-- Nothing back here can take focus or receive clicks -->
</main>
<dialog open>
  <h2>Rename workspace</h2>
  <!-- Focus is confined to this subtree -->
</dialog>
```

The platform `<dialog>` element gives you the same thing directly:

```javascript
const sheet = document.querySelector('dialog');
sheet.showModal();  // Traps focus on open, dismisses on Escape
```

## Native Popovers

Tooltips, menus, and other non-modal overlays should ride on the built-in popover:

```html
<button popovertarget="share-menu">Share</button>
<div id="share-menu" popover>
  <button>Copy link</button>
  <button>Send by email</button>
</div>
```

You get light-dismiss for free (a click outside closes it), sane stacking with no z-index escalation, and accessible behavior out of the box.

## Placing Dropdowns And Overlays

A dropdown positioned with `position: absolute` inside an ancestor carrying `overflow: hidden` or `overflow: auto` gets clipped. Of every dropdown defect that shows up in generated code, this one appears the most.

### Tethering With CSS Anchors

The current answer ties an overlay to its trigger declaratively, with no JavaScript involved:

```css
.share-button {
  anchor-name: --share-trigger;
}

.share-panel {
  position: fixed;
  position-anchor: --share-trigger;
  position-area: block-end span-inline-end;
  margin-top: 4px;
}

/* When the space below runs out, go above */
@position-try --above {
  position-area: block-start span-inline-end;
  margin-bottom: 4px;
}
```

`position: fixed` is what lets the panel break out of any ancestor's `overflow` clipping, while `@position-try` deals with viewport edges on its own. **Support today**: Chrome 125+ and Edge 125+. Firefox and Safari have not shipped it, so pair it with a fallback for those engines.

### Pairing Popover With Anchors

Layer the Popover API on top of anchor positioning and a single pattern delivers correct placement, stacking, light-dismiss, and accessibility together:

```html
<button popovertarget="share-menu" class="share-button">Share</button>
<div id="share-menu" popover class="share-panel">
  <button>Copy link</button>
  <button>Send by email</button>
</div>
```

The `popover` attribute promotes the element into the **top layer**, which renders above everything else no matter what z-index or overflow rules apply below it. No portal required.

### Portals And Teleports

Component frameworks can instead mount the dropdown at the document root and place it from JavaScript:

- **React** hands you `createPortal(dropdown, document.body)`
- **Vue** wraps the overlay in `<Teleport to="body">`
- **Svelte** has no built-in, so use a portal library or mount onto `document.body` yourself

Derive the coordinates from the trigger's `getBoundingClientRect()`, then set `position: fixed` with the resulting `top` and `left`. Recompute whenever the page scrolls or the window resizes.

### Falling Back To Fixed Positioning

Where anchor positioning is unavailable, manual coordinates on `position: fixed` still sidestep overflow clipping:

```css
.share-panel {
  position: fixed;
  /* JS assigns top/left from the trigger's getBoundingClientRect() */
}
```

Test the viewport edges before you paint. When the panel would spill past the bottom, flip it above the trigger; when it would spill past the right edge, align its right side to the trigger's instead.

### What Not To Do

- **`position: absolute` nested in `overflow: hidden`** — guaranteed clipping. Switch to `position: fixed` or the top layer.
- **Magic numbers such as `z-index: 9999`** — replace them with a named scale: `dropdown (100) -> sticky (200) -> modal-backdrop (300) -> modal (400) -> toast (500) -> tooltip (600)`.
- **Leaving the dropdown markup inline** with no way out of the parent's stacking context. Pick one escape hatch: `popover` for the top layer, a portal, or `position: fixed`.

## Undo Beats Confirmation

Confirmation dialogs get dismissed on autopilot, which makes undo the stronger safety net. Drop the item from the interface at once, surface an undo toast, and only commit the deletion after that toast times out. Keep a confirmation step for the cases that genuinely warrant one: actions that cannot be reversed such as deleting an account, actions that are expensive to get wrong, and bulk operations.

## Keyboard Movement Within Components

### The Roving Tabindex

Inside a set of related controls — tab strips, menu items, radio groups — exactly one member is tabbable and arrow keys travel between the rest:

```html
<div role="tablist">
  <button role="tab" tabindex="0">Overview</button>
  <button role="tab" tabindex="-1">Usage</button>
  <button role="tab" tabindex="-1">Billing</button>
</div>
```

The arrow keys hand `tabindex="0"` from one member to the next; pressing Tab exits the group and lands on the following component.

### Links That Skip The Chrome

Give keyboard users a way past the navigation with a skip link such as `<a href="#main-content">Skip to main content</a>`. Park it off-screen and reveal it when it receives focus.

## Making Gestures Discoverable

Swipe-to-delete and gestures like it leave no trace on screen, so plant clues that they exist:

- **Peek**: let the delete button show at the edge
- **Teach**: coach marks the first time the surface is used
- **Duplicate the path**: keep a visible equivalent, for example a menu carrying "Delete"

A gesture should never be the sole route to an action.

---

**Steer clear of**: focus indicators removed with nothing offered in their place; placeholder text pressed into service as a label; targets that miss current accessibility requirements or are simply awkward to hit; error messages too vague to act on; and custom controls shipped without native semantics, accessible names, and keyboard support.
