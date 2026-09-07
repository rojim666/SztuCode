---
name: Spatial Design
description: Spacing scales built on a 4pt base, density handling, margin and padding rules, alignment grids, and optical spacing corrections.
---

## Contents

- [Spacing Scale](#spacing-scale)
- [Layout Grids](#layout-grids)
- [Component-Level Breakpoints](#component-level-breakpoints)
- [Reading Order](#reading-order)
- [Optical Corrections](#optical-corrections)
- [Layering and Shadow](#layering-and-shadow)
- [Habits to Break](#habits-to-break)


# Spatial Design

## Spacing Scale

### Build on 4pt, Not 8pt

A scale stepping in 8s leaves gaps you will keep bumping into — 12px sits right between 8 and 16 and comes up constantly. Step in 4s instead, giving you 4, 8, 12, 16, 24, 32, 48, 64, 96px.

### Let Token Names Describe Roles

A token should say what a gap is for, not how many pixels it holds: prefer `--space-sm` and `--space-lg` over `--spacing-8`. When separating siblings, reach for `gap` rather than margins — no collapsing margins, and no last-child cleanup rules.

## Layout Grids

### A Grid That Reflows Itself

`repeat(auto-fit, minmax(280px, 1fr))` gives you a responsive grid and requires no breakpoints at all: every column holds at 280px or wider, the row fits as many as it can, and remaining space is distributed across them. When the layout gets genuinely complex, describe it with named regions via `grid-template-areas` and restate those regions per breakpoint.

## Component-Level Breakpoints

Reserve viewport queries for page-level structure. **A component should respond to the box it sits in**:

```css
.panel-shell {
  container-type: inline-size; /* makes this box a query target */
}

.panel {
  display: grid;
  gap: var(--space-md);
}

/* Responds to the width of .panel-shell, not the window */
@container (min-width: 400px) {
  .panel {
    grid-template-columns: 120px 1fr;
  }
}
```

**The payoff**: drop that same panel into a cramped sidebar and it stays compact; drop it into the main column and it opens up — no viewport-based workarounds required.

## Reading Order

### Blur It and Look Again

Squint at the screen, or take a screenshot and blur it. Three questions:
- Which element is clearly first?
- Which one is clearly second?
- Do the groupings hold together?

A blurred view where everything carries equal weight is a hierarchy that does not exist.

### Stack Several Signals, Not Just One

Size on its own rarely does the job. Layer these instead:

| Dimension | Reads clearly | Reads flat |
|---|---|---|
| **Scale** | 3:1 ratio or greater | anything below 2:1 |
| **Weight** | Bold against Regular | Medium against Regular |
| **Color** | strongly contrasting | neighbouring tones |
| **Placement** | top or left for the primary | bottom or right |
| **Whitespace** | isolated by open space | packed in tight |

**Two or three signals working together beat any one of them alone**: a heading that is bigger, heavier, and given extra room above it.

### You Probably Do Not Need a Card

Cards get reached for far too readily — spacing and alignment already group content on their own. Save cards for the cases that call for them: content that is genuinely self-contained and actionable, items being compared side by side in a grid, or a region that needs an unmistakable interaction boundary. **A card inside another card is never the answer** — differentiate within a card using spacing, type, and understated dividers.

## Optical Corrections

Set text flush at `margin-left: 0` and it will still read as slightly indented, because the letterforms carry their own side bearing; a small negative margin around `-0.05em` pulls it into true alignment. The same illusion affects icons: centering one geometrically often looks wrong, so a play triangle wants nudging to the right, and arrows want nudging the way they point.

### Tap Area Beyond the Visible Edge

A control can be visually tiny and still owe the user a 44px minimum target. Get there with padding, or with a pseudo-element:

```css
.glyph-btn {
  position: relative;
  width: 24px;   /* what the eye sees */
  height: 24px;  /* likewise */
}

.glyph-btn::before {
  content: '';
  position: absolute;
  inset: -10px;  /* grows the hit area out to 44px */
}
```

## Layering and Shadow

Give z-index a semantic ladder rather than arbitrary integers: dropdown, then sticky, then modal-backdrop, then modal, then toast, then tooltip. Shadows deserve the same treatment — one elevation scale running sm, md, lg, xl. **Worth remembering**: a shadow you can plainly make out has almost certainly been pushed too far.

## Habits to Break

Three of them: spacing values invented outside the scale; spacing applied uniformly everywhere, when variation is exactly what produces hierarchy; and hierarchy attempted through size alone rather than size, weight, color, and space working together.
