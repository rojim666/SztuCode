---
name: Responsive Design
description: Building up from the small screen — breakpoint strategy, fluid type and spacing with clamp, container queries, input-capability queries, and layout patterns that rearrange cleanly.
---

## Contents

- [Start From the Small Screen](#start-from-the-small-screen)
- [Let Content Choose the Breakpoints](#let-content-choose-the-breakpoints)
- [Query Input Capability, Not Screen Width](#query-input-capability-not-screen-width)
- [Serving the Right Image](#serving-the-right-image)
- [Drawing Around the Notch](#drawing-around-the-notch)
- [How Layouts Should Rearrange](#how-layouts-should-rearrange)
- [Emulators Are Not Devices](#emulators-are-not-devices)


# Responsive Design

## Start From the Small Screen

Let the base rules describe the phone, then layer complexity upward with `min-width`. Reverse that with `max-width` and every phone pays first for desktop styling it never uses.

## Let Content Choose the Breakpoints

Device catalogs make poor breakpoints. Narrow the viewport, widen it slowly, and break wherever the layout falls apart. Three usually cover it — 640, 768, 1024px. Anything that can scale continuously belongs in `clamp()` instead, no breakpoint required.

## Query Input Capability, Not Screen Width

**Width says nothing about how the thing is operated.** Touchscreen laptops and keyboard-attached tablets break that assumption, so ask about pointer and hover directly:

```css
/* Precise pointer: mouse or trackpad */
@media (pointer: fine) {
  .toolbar-action { padding: 8px 16px; }
}

/* Imprecise pointer: finger or stylus */
@media (pointer: coarse) {
  .toolbar-action { padding: 12px 20px; }  /* Bigger hit area */
}

/* Hover is available */
@media (hover: hover) {
  .tile:hover { transform: translateY(-2px); }
}

/* Hover is unavailable, as on touch */
@media (hover: none) {
  .tile { /* Skip hover styling; express the state on :active */ }
}
```

**Critical**: never gate a feature behind hover — a touch user cannot trigger it.

## Serving the Right Image

### Width descriptors in srcset

```html
<img
  src="banner-800.jpg"
  srcset="
    banner-400.jpg 400w,
    banner-800.jpg 800w,
    banner-1200.jpg 1200w
  "
  sizes="(max-width: 768px) 100vw, 50vw"
  alt="Product banner"
>
```

**What each part does**:
- `srcset` lists the files with their true pixel widths, marked by `w` descriptors
- `sizes` declares the width the image will occupy once laid out
- The browser combines both with viewport width and device pixel ratio to pick a file

### `<picture>` when the crop itself must change

For a different composition, not merely a different resolution:

```html
<picture>
  <source media="(min-width: 768px)" srcset="landscape-crop.jpg">
  <source media="(max-width: 767px)" srcset="portrait-crop.jpg">
  <img src="default-crop.jpg" alt="...">
</picture>
```

## Drawing Around the Notch

Phones ship with cutouts, curved corners, and home indicators. Reserve room via `env()`:

```css
body {
  padding-top: env(safe-area-inset-top);
  padding-bottom: env(safe-area-inset-bottom);
  padding-left: env(safe-area-inset-left);
  padding-right: env(safe-area-inset-right);
}

/* Guarantee a minimum where the inset is zero */
.sticky-bar {
  padding-bottom: max(1rem, env(safe-area-inset-bottom));
}
```

None of it applies until the viewport meta opts in with **viewport-fit**:
```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
```

## How Layouts Should Rearrange

**Navigation** runs through three stages: hamburger plus drawer on phones, compact horizontal bar on tablets, full labeled version on desktop. **Tables** stop being tables on small screens — switch rows to `display: block` and carry column names in `data-label` so each record reads as a card. **Progressive disclosure** folds away whatever mobile can hide; `<details>`/`<summary>` gives you that for free.

## Emulators Are Not Devices

DevTools emulation checks layout, but cannot show you:

- Real touch interaction
- The CPU and memory the device actually has
- Latency on a real network
- Font rendering differences
- Browser chrome and the on-screen keyboard appearing

**Minimum hardware**: one physical iPhone, one physical Android, plus a tablet where the product warrants it. Budget Android handsets expose performance problems no simulator reproduces.

---

**Steer clear of**: designing desktop-down; sniffing devices instead of detecting features; split mobile and desktop codebases; leaving tablet and landscape untested; assuming every mobile device is fast.
