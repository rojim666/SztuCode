---
name: overdrive
description: Take an interface further than convention allows through technically ambitious work — shaders, spring physics, scroll-driven reveals, animation held at 60fps. Use when the ask is to impress, to go all-out, or to build something that feels extraordinary.
---

## Contents

- [MANDATORY PREPARATION](#mandatory-preparation)
- [Decide What Counts as Extraordinary Here](#decide-what-counts-as-extraordinary-here)
- [Technique Catalog](#technique-catalog)
- [Build It Responsibly](#build-it-responsibly)
- [Test Whether It Landed](#test-whether-it-landed)


Take the interface somewhere convention would not go. Effects are only part of it; the real material is everything the browser can do — a table that stays fluid across a million rows, a dialog that grows out of the control that opened it, a form whose validation streams back as you type, a page change that plays like a cut in a film.

## MANDATORY PREPARATION

Before proceeding, apply the main SKILL.md priorities. Use Design Context from the current instructions or `.uicraft.md` when available. If high-impact product or brand context is still missing, read [uicraft-init.md](uicraft-init.md) and ask only focused questions; otherwise state conservative assumptions and continue.

**EXTRA IMPORTANT FOR THIS SKILL**: what qualifies as extraordinary is set by the context. Particles on a creative portfolio read as impressive; those same particles on a settings screen read as embarrassing. Yet a settings screen whose saves land optimistically and whose states animate between each other is extraordinary in its own right. Learn the project's personality and goals before you pick a direction.

### Pitch the Direction First

The failure risk on this workflow is high. Where the user has already named a direction and its constraints, run with it. Where they have not:

1. **Work up 2-3 candidate directions** — vary the technique, the level of ambition, and the aesthetic. Sketch in a sentence or two how each one would look and feel in use.
2. Lay the options out, cover the trade-offs in browser support, runtime cost, and complexity, and let the user pick before you commit real code.
3. Build only the direction they confirmed.

Skip this and you risk investing in something embarrassing that has to be discarded.

### Refine It in a Real Browser

First attempts at ambitious effects are almost always wrong. You MUST drive the browser automation tools to render the work, look at it, and refine. Never take on faith that the effect reads correctly — go and confirm. Plan for several passes. What separates "the code runs" from "this looks extraordinary" is visual iteration, and nothing else gets you there.

---

## Decide What Counts as Extraordinary Here

Which flavor of ambition fits depends completely on the surface in front of you. Before reaching for a technique, answer this: **what would make someone using THIS interface stop and say "that's nice"?**

### Visual and marketing surfaces
On pages, hero sections, landing pages, and portfolios the reaction is usually sensory — a reveal choreographed to scroll, a shader running behind the content, a page transition with cinematic pacing, generative artwork that answers the cursor.

### Functional UI
On tables, forms, dialogs, and navigation the reaction comes from feel: a dialog that morphs out of its triggering button through View Transitions, a grid holding 60fps across 100k virtualized rows, validation that streams in fast enough to feel instantaneous, dragging that carries real spring physics.

### Performance-critical UI
Here the reaction is felt without being seen — filtering 50k records with no flicker, a heavy form that never once blocks the main thread, an editor whose image operations land near-instantly. The interface simply never pauses.

### Data-heavy interfaces
For charts and dashboards it comes down to fluidity: Canvas or WebGL pushing large datasets through the GPU, transitions animating from one data state to the next, force-directed graphs that settle into place naturally.

**What unites them**: some part of the build exceeds what a person expects from a web page. The technique exists to serve the experience, never the reverse.

## Technique Catalog

Grouped by the outcome you want rather than by technology label.

Support shifts over time. Before committing to anything below, confirm its current status against primary documentation, gate it behind feature detection, and decide on a fallback. Keep browser-version assertions out of the implementation plan.

### Give transitions cinematic weight
- **View Transitions API** — shared-element transitions across states or across documents where support exists. Fall back to a conventional transition or an instant state change.
- **`@starting-style`** — animate entry transitions where supported, including elements that are becoming visible. Retain a static fallback.
- **Spring physics** — motion described by mass, tension, and damping rather than a cubic-bezier curve. Reach for motion (previously Framer Motion), GSAP, or a spring solver you write yourself.

### Bind animation to scroll position
- **Scroll-driven animations** (`animation-timeline: scroll()`) — parallax, progress, and reveal sequences expressed in CSS where supported. A static fallback is always required.

### Render past what CSS can do
- **WebGL** — shaders, post-processing, and particle systems, once you have confirmed a usable graphics context. Three.js, OGL, and regl are the common libraries.
- **WebGPU** — current-generation GPU rendering and compute where it is supported. Pick a fallback that suits the experience — WebGL2, Canvas, CSS, or a static visual — and never assume a WebGL implementation will always be workable.
- **Canvas 2D / OffscreenCanvas** — bespoke rendering, per-pixel work, or shifting expensive rendering off the main thread completely by pairing Web Workers with OffscreenCanvas.
- **SVG filter chains** — displacement maps, turbulence, and morphology for organic distortion, all animatable from CSS.

### Bring large datasets to life
- **Virtual scrolling** — draw only the rows in view for tables and lists running to tens of thousands of entries. Simple cases need no dependency; TanStack Virtual handles the complicated ones.
- **GPU-accelerated charts** — Canvas- or WebGL-rendered visualization once a dataset outgrows SVG and the DOM. deck.gl or a custom regl-based renderer will do it.
- **Animated data transitions** — morph one chart state into the next instead of swapping it out. Use D3's `transition()`, or View Transitions for DOM-based charts.

### Animate properties that resist animation
- **`@property`** — register typed custom properties where supported so values that would not otherwise interpolate cleanly can be animated.
- **Web Animations API** — timelines driven from JavaScript that compose, cancel, and reverse, where supported.

### Push past performance limits
- **Web Workers** — relocate computation off the main thread: bulk data processing, image manipulation, search indexing, anything that would otherwise cause jank.
- **OffscreenCanvas** — do the drawing inside a worker so the main thread stays free while demanding visuals render behind it.
- **WASM** — near-native speed for computation-bound features such as image processing, physics simulation, and codecs.

### Reach into the device
- **Web Audio API** — spatialized audio, audio-reactive visuals, sonic feedback. A user gesture is required before it can start.
- **Device APIs** — orientation, ambient light, geolocation. Use them rarely, and only with permission granted.

**NOTE**: the scope here is how an interface FEELS, not what the product DOES. Real-time collaboration, offline support, and new backend capability are product decisions rather than UI enhancements. Stay on making the features that already exist feel extraordinary.

## Build It Responsibly

### Progressive enhancement is not optional

Every technique has to degrade cleanly, and the version without the enhancement still has to be good.

```css
@supports (animation-timeline: scroll()) {
  .parallax-band { animation-timeline: scroll(); }
}
```

```javascript
if ('gpu' in navigator) { /* WebGPU path */ }
else if (surface.getContext('webgl2')) { /* Step down to WebGL2 */ }
/* And the CSS-only path still has to look good */
```

### Frame-rate discipline

- Hold 60fps. Once it slips under 50, cut complexity.
- Honor `prefers-reduced-motion` without exception, and give it a static alternative that is genuinely beautiful.
- Defer construction of expensive resources — WebGL contexts, WASM modules — until the element is close to the viewport.
- Stop rendering what has scrolled out of sight. If it cannot be seen, it should not be drawn.
- Validate on actual mid-range hardware, not on your development machine.

### Polish makes the difference

"Cool" becomes "extraordinary" in the final 20% of refinement — the easing on a spring, the offsets that stagger a reveal, the small secondary movement that lends a transition physicality. Do not ship the first build that works; ship the one that feels inevitable.

**Hard limits**:
- `prefers-reduced-motion` is an accessibility requirement, not advice; honor it.
- Nothing ships if it janks on mid-range hardware.
- No bleeding-edge API goes in without a working fallback.
- Audio plays only after the user opts in explicitly.
- Technical ambition must never paper over weak design fundamentals — repair those first with the other skills.
- Do not stack competing extraordinary moments; focus is what creates impact, and excess only creates noise.

## Test Whether It Landed

- **The wow test**: put it in front of fresh eyes. Is there a reaction?
- **The removal test**: strip it out. Is the experience poorer, or does no one notice?
- **The device test**: try a phone, a tablet, a Chromebook. Does it stay smooth?
- **The accessibility test**: switch on reduced motion. Is it still beautiful?
- **The context test**: is this right for THIS brand and THIS audience?

Being technically extraordinary has little to do with adopting the newest API. It comes from making an interface do something people did not believe a website could do.
