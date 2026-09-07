---
name: Motion Design
description: Durations for interface animation (the 100/300/500 rule), curve selection, arrival and departure patterns, waiting states, and motion accessibility.
---

# Motion Design

## Contents

- [Pick the Duration Before the Curve](#pick-the-duration-before-the-curve)
- [Choosing an Easing Curve](#choosing-an-easing-curve)
- [Animate Transform and Opacity, Nothing Else](#animate-transform-and-opacity-nothing-else)
- [Sequencing Lists with Stagger](#sequencing-lists-with-stagger)
- [Honoring Reduced Motion](#honoring-reduced-motion)
- [Reveal Animations Must Fail Open (Critical)](#reveal-animations-must-fail-open-critical)
- [Engineering the Feeling of Speed](#engineering-the-feeling-of-speed)
- [Runtime Cost](#runtime-cost)

## Pick the Duration Before the Curve

Length carries more weight than the curve you pick. Nearly all interface motion belongs in one of four windows:

| Window | What it covers | Typical cases |
|:--|:--|:--|
| **100-150ms** | Immediate acknowledgement | Toggle flip, button press, color swap |
| **200-300ms** | State changes | Menu opening, tooltip, hover response |
| **300-500ms** | Layout shifts | Accordion, modal, drawer |
| **500-800ms** | Arrivals | Page load, hero reveal |

Departures should outpace arrivals — budget roughly three quarters of the entrance duration for the exit.

## Choosing an Easing Curve

Skip the bare `ease` keyword. It splits the difference and is rarely the best answer for any specific job. Reach for a deliberate curve instead:

| Curve family | Applies to | cubic-bezier |
|:--|:--|:--|
| **ease-out** | Content arriving | `cubic-bezier(0.16, 1, 0.3, 1)` |
| **ease-in** | Content departing | `cubic-bezier(0.7, 0, 0.84, 0)` |
| **ease-in-out** | Toggles that travel out and come back | `cubic-bezier(0.65, 0, 0.35, 1)` |

Small interactions read as natural under exponential curves, because friction and deceleration in the physical world behave the same way:

```css
/* Quart — even and refined; the sensible default */
--ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1);

/* Quint — a shade more theatrical */
--ease-out-quint: cubic-bezier(0.22, 1, 0.36, 1);

/* Expo — decisive, almost abrupt */
--ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
```

Treat measured deceleration as the baseline. Spring, elastic, and bouncing motion steal attention from the content once they are applied broadly, so reserve them for the cases where brand voice, the physics of the interaction itself, or direct user feedback justify the choice. Where you do use them, keep the overshoot restrained and still respect reduced-motion preferences.

## Animate Transform and Opacity, Nothing Else

Every other property drags a layout recalculation along with it, so confine animation to `transform` and `opacity`. When an accordion has to grow, transition `grid-template-rows` from `0fr` to `1fr` rather than animating `height` directly.

## Sequencing Lists with Stagger

Drive the offset from a custom property: put `style="--i: 0"` on each item and write `animation-delay: calc(var(--i, 0) * 50ms)`. **Keep an eye on the total** — ten items at 50ms burns 500ms before the last one so much as moves. Beyond that, either shrink the per-item step or stop staggering after the first handful.

## Honoring Reduced Motion

Treat this as a requirement rather than a nicety: roughly 35% of adults past 40 live with some vestibular condition.

```css
/* Author the full-motion version as usual */
.tile {
  animation: rise 500ms ease-out;
}

/* Swap in a travel-free equivalent */
@media (prefers-reduced-motion: reduce) {
  .tile {
    animation: dissolve 200ms ease-out;  /* Crossfade, no displacement */
  }
}

/* Or switch everything off wholesale */
@media (prefers-reduced-motion: reduce) {
  *, *::after, *::before {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

Animations that carry information stay: progress bars, spinners (run them slower), and focus indicators keep working — they simply give up their spatial movement.

## Reveal Animations Must Fail Open (Critical)

The usual scroll-reveal recipe parks content at `opacity: 0` and waits for JavaScript — typically an `IntersectionObserver` — to attach an `.in` or `.visible` class that fades it in. **That inverts the safe default: the page ships invisible and stakes every word of it on one script executing cleanly.** One syntax error, one exception thrown before the observer is wired up, a visitor with scripting off, or a crawler, and the page stays **blank forever** — a total loss triggered by what was only ever meant to be decoration.

**The rule: whether content is visible must never hinge on JavaScript succeeding.** Animation is free to shape *how* content shows up, but the text has to be readable when scripts fail, are turned off, or simply have not run yet. Pick one of these fail-open approaches.

**Option A — pure CSS, and the one to prefer.** Let a CSS animation carry the entrance and terminate in the visible state, so a page where JS never executes still settles at `opacity: 1`:

```css
.on-enter { animation: enter-lift 600ms var(--ease-out-quart) both; }
@keyframes enter-lift { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .on-enter { animation: none; } }
```

**Option B — hide only once JS proves it is alive.** Stamp a marker class such as `has-js` onto `<html>` from the very first script on the page, then scope every hidden state beneath it. Sessions without working JavaScript never enter the hidden state at all:

```html
<script>document.documentElement.classList.add('has-js');</script>
```
```css
/* The start-hidden state exists only for script-confirmed sessions */
.has-js .on-enter { opacity: 0; transform: translateY(16px); transition: opacity .6s, transform .6s; }
.has-js .on-enter.shown { opacity: 1; transform: none; }
@media (prefers-reduced-motion: reduce) { .has-js .on-enter { opacity: 1; transform: none; transition: none; } }
```

The anti-pattern to reject outright: a naked `.on-enter { opacity: 0 }` in the stylesheet whose only route back to `opacity: 1` runs through a class that a script adds. Any throw in that script and the page renders nothing.

Then make the reveal script itself defensive:

- Put the observer setup inside `try/catch`, and have the `catch` branch reveal everything at once (`document.querySelectorAll('.on-enter').forEach(function(el){ el.classList.add('shown'); })`). A failure should cost you the animation, never the content.
- Detect a missing `IntersectionObserver` and fall back to showing all elements straight away.
- Mind the shape of the script: `return` at top level is a `SyntaxError`, and it is only legal inside a function. If your reduced-motion or no-observer branch bails out with an early `return`, that code **must** live inside a function or IIFE — otherwise the parse error kills the whole script, which (paired with the anti-pattern above) leaves a blank page.

## Engineering the Feeling of Speed

**Actual speed is invisible to users; perceived speed is all they respond to.** Shaping perception buys as much as shaving milliseconds.

**80ms is the instant threshold.** Sensory input is buffered by the brain for about 80ms so that it can be synchronized, which means anything landing inside that window registers as simultaneous with the action that caused it. Aim there for micro-interactions.

**Trade passive waiting for active engagement.** Time spent watching a spinner stretches; time spent watching something happen does not. Three ways to shift the balance:

- **Start before you are ready** — kick off the transition the moment loading begins, the way iOS zooms an app open or a skeleton frame appears. Work looks like it is already underway.
- **Finish in pieces** — render progressively instead of holding everything back until the last byte arrives. Buffered video, progressive images, and streamed HTML all work this way.
- **Assume success** — commit the interface change immediately and reconcile failures afterward. An Instagram like registers offline, updating instantly and syncing later. Suitable for low-stakes actions; keep it away from payments and destructive operations.

**Curves bend perceived duration too.** Because the peak-end effect weights the closing moments heavily, ease-in — accelerating into completion — makes an operation feel shorter. Entrances still feel best with ease-out, but easing *into* the end of a task compresses how long it seemed to take.

**One caveat**: instant is not always better. For work users expect to be hard — search, analysis — an immediate answer can read as suspicious and cheapen the result. A short, visible pause sometimes reads as evidence of real computation.

## Runtime Cost

Hold `will-change` back until motion is actually about to start (`:hover`, `.animating`) rather than declaring it up front. Prefer Intersection Observer to scroll listeners for scroll-driven animation, and unobserve each element after its one-time reveal. Define motion tokens — durations, easings, the transitions you reuse — so timing stays consistent across the product.

---

**Failure modes to watch for**: motion on everything (fatigue sets in fast); feedback animations that run past 500ms; `prefers-reduced-motion` left unhandled; animation used as camouflage for a slow load.
