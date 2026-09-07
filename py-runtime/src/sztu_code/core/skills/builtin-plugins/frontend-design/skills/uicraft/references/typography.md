---
name: Typography
description: Enduring rules of type for interfaces — rhythm in the vertical axis, size scales that step cleanly, pairing typefaces, measure, and building readable hierarchy.
---

## Contents

- [Foundations of the Type System](#foundations-of-the-type-system)
- [Picking and Combining Typefaces](#picking-and-combining-typefaces)
- [Type on the Modern Web](#type-on-the-modern-web)
- [Legibility and Access](#legibility-and-access)
- [Tokenizing Typography](#tokenizing-typography)


# Typography

## Foundations of the Type System

### Rhythm on the Vertical Axis

Let the computed line-height drive every piece of vertical spacing. Body copy at `16px` with `line-height: 1.5` resolves to 24px, so margins, padding, and gaps should land on 24px multiples. Readers never notice the grid consciously but they feel it: type and whitespace share one arithmetic.

### Stepping the Scale

Where teams usually go wrong is shipping a pile of near-identical sizes — 14px, 15px, 16px, 18px — which flattens hierarchy into mush.

**Trade quantity for contrast.** Five steps handle almost every layout:

| Step | Suggested Size | Where It Lands |
|------|----------------|----------------|
| xs | 0.75rem | Captions, legal, fine print |
| sm | 0.875rem | Metadata, secondary UI chrome |
| base | 1rem | Running body copy |
| lg | 1.25-1.5rem | Lead paragraphs, subheadings |
| xl+ | 2-4rem | Hero and headline type |

Choose a single interval and hold to it. The conventional options are 1.25 (major third), 1.333 (perfect fourth), and 1.5 (perfect fifth).

### Measure and Comfort

Cap the measure in `ch` units rather than pixels, so it tracks character count — `max-width: 65ch`. Leading and measure move in opposite directions: a narrow column reads better tightly set, while a wide column needs looser leading to keep the eye from skipping rows.

**Easy to miss**: light-on-dark type reads thinner than dark-on-light, so it wants extra air. Nudge line-height up by 0.05-0.1 whenever you invert the palette.

## Picking and Combining Typefaces

### Getting Past the Defaults

**Inter, Roboto, Open Sans, Lato, and Montserrat have become invisible.** They saturate the web, so reaching for one guarantees a generic result. Fine for documentation and internal tools, where character is beside the point — but a distinctive interface has to look further afield.

**Stronger picks from Google Fonts**:
- Swap Inter for **Instrument Sans**, **Plus Jakarta Sans**, or **Outfit**
- Swap Roboto for **Onest**, **Figtree**, or **Urbanist**
- Swap Open Sans for **Source Sans 3**, **Nunito Sans**, or **DM Sans**
- Reach for **Fraunces**, **Newsreader**, or **Lora** when the brief calls for editorial or premium

**Don't overlook the system stack.** `-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui` renders natively, costs zero network time, and is extremely legible — the right call whenever performance outranks personality.

### How to Pair (and When Not To)

**A second typeface is optional far more often than people assume.** One well-chosen family across several weights usually yields a cleaner hierarchy than two families fighting each other. Add a second face only for real separation — say, a display cut for headlines over a serif body.

If you do pair, make the two differ along an explicit axis:
- Structure: serif against sans
- Personality: geometric against humanist
- Proportion: condensed display against wide body copy

Pairs that are merely *similar* — two geometric sans-serifs, for instance — are the worst outcome. They read as tension rather than hierarchy, so rule them out.

### Loading Web Fonts Without the Jump

Late-arriving fonts reflow the page and users watch content shift under their eyes. Two settings solve it:

```css
/* 1. Keep text painted while the file downloads */
@font-face {
  font-family: 'BrandSans';
  src: url('brand-sans.woff2') format('woff2');
  font-display: swap;
}

/* 2. Tune the fallback so the swap barely moves anything */
@font-face {
  font-family: 'BrandSans-Fallback';
  src: local('Arial');
  size-adjust: 105%;        /* Align x-height */
  ascent-override: 90%;     /* Align ascenders */
  descent-override: 20%;    /* Align descenders */
  line-gap-override: 10%;   /* Align line spacing */
}

body {
  font-family: 'BrandSans', 'BrandSans-Fallback', sans-serif;
}
```

You can derive those override percentages mechanically with [Fontaine](https://github.com/unjs/fontaine).

## Type on the Modern Web

### Fluid Sizing — Where It Belongs

`clamp(min, preferred, max)` interpolates type size against viewport width. The preferred term (something like `5vw + 1rem`) sets the scaling rate — raise the vw component for a steeper curve, and always carry a rem term so the value never collapses to zero on small screens.

**Reach for fluid type on** headlines and display copy in marketing and editorial pages, where the text is the layout and needs room to expand.

**Stay on fixed `rem` steps for** product UI, dashboards, and dense data views. No major system — Material, Polaris, Primer, Carbon — applies fluid type inside product surfaces; a fixed scale, adjusted at breakpoints if needed, gives container-driven layouts the spatial predictability they need. Keep body copy fixed on marketing pages too: the delta between viewports is too small to be worth it.

### OpenType Features Worth Wiring Up

These ship in most fonts and almost nobody enables them. They are cheap polish:

```css
/* Digits that align in columns */
.metrics-grid { font-variant-numeric: tabular-nums; }

/* Real fractions instead of slashed digits */
.dosage-note { font-variant-numeric: diagonal-fractions; }

/* Abbreviations set in small caps */
abbr { font-variant-caps: all-small-caps; }

/* Turn off ligatures where glyph identity matters */
code { font-variant-ligatures: none; }

/* Kerning is normally on — declare it anyway */
body { font-kerning: normal; }
```

To see which features a given font actually ships, inspect it with [Wakamai Fondue](https://wakamaifondue.com/).

## Legibility and Access

Contrast ratios are covered to death elsewhere. These four get skipped:

- **Leave pinch-zoom alone.** `user-scalable=no` is an accessibility failure. When the layout falls apart at 200% zoom, repair the layout rather than locking the viewport.
- **Size text in rem or em**, which honors whatever default the reader set in their browser. Body copy should never be sized in `px`.
- **Hold body text at 16px or above.** Anything smaller tires the eye and trips WCAG on mobile.
- **Give text links a real hit area.** Padding or line-height should push the tappable region to 44px or more.

## Tokenizing Typography

Token names should describe role, not measurement: `--text-body` and `--text-heading` rather than `--font-size-16`. A complete type token set covers font stacks, the size scale, weights, line-heights, and letter-spacing.

---

**Steer clear of**: carrying more than two or three families in one project; declaring a webfont with no fallback behind it; treating FOUT/FOIT as someone else's problem; and setting body copy in a display or decorative face.
