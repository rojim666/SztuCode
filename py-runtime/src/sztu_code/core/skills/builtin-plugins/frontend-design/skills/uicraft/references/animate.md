---
name: animate
description: Go through a feature and layer in motion that earns its place — purposeful animation, micro-interactions, and transitions that aid usability and add delight. Use when the user raises adding animation, transitions, micro-interactions, motion design, hover effects, or making the UI feel more alive.
---

## Contents

- [MANDATORY PREPARATION](#mandatory-preparation)
- [Find Where Motion Would Help](#find-where-motion-would-help)
- [Shape the Motion Plan](#shape-the-motion-plan)
- [Build the Motion by Category](#build-the-motion-by-category)
- [Craft and Technique](#craft-and-technique)
- [Check the Result](#check-the-result)


Study a feature, then place animation and micro-interaction where they sharpen comprehension, close feedback loops, and give it a pulse.

## MANDATORY PREPARATION

Before proceeding, apply the main SKILL.md priorities. Use Design Context from the current instructions or `.uicraft.md` when available. If high-impact product or brand context is still missing, read [uicraft-init.md](uicraft-init.md) and ask only focused questions; otherwise state conservative assumptions and continue. Additionally gather: performance constraints.

---

## Find Where Motion Would Help

Find the places movement would genuinely improve.

1. **Locate the dead spots**:
   - **Unacknowledged actions**: user actions the interface never visually confirms — button presses, form submissions, and the like
   - **Abrupt cuts**: state flips with no transition — showing and hiding, page loads, route changes
   - **Ambiguous relationships**: spatial or hierarchical connections the layout leaves implicit
   - **Joyless mechanics**: interactions that work correctly yet feel like nothing
   - **Unguided moments**: where motion could steer attention or explain behavior

2. **Pin down the context**:
   - Product personality — playful or serious, energetic or calm?
   - Performance budget — mobile-first, or an already heavy page?
   - Audience — motion-sensitive users in scope, or power users who want speed?
   - Emphasis — one signature animation, or a spread of small ones?

Where the codebase leaves that ambiguous, ask the user directly to clarify what you cannot infer.

**CRITICAL**: `prefers-reduced-motion` is non-negotiable — always ship a non-animated path for those who need one.

## Shape the Motion Plan

Decide what the motion is for before writing any:

- **Hero moment**: the one signature animation — page load, hero section, a pivotal interaction?
- **Feedback layer**: which interactions must acknowledge themselves?
- **Transition layer**: which state changes need their edges smoothed?
- **Delight layer**: where is there room to surprise?

**IMPORTANT**: One well-choreographed sequence beats animation sprinkled everywhere. Spend the budget on high-impact moments.

## Build the Motion by Category

Work the categories in order.

### Entrances

- **Page load choreography**: stagger reveals at 100-150ms offsets, pairing fade with slide
- **Hero section**: a dramatic entrance for primary content — scale, parallax, or something inventive
- **Content reveals**: trigger on scroll via intersection observer
- **Modal and drawer entry**: slide and fade together, fade the backdrop, manage focus

### Small interactive responses

- **Buttons**:
  - Hover: restrained scale of 1.02-1.05, a color shift, a deeper shadow
  - Click: quick dip and recover (0.95 → 1), optionally a ripple
  - Loading: hand over to a spinner or a pulse
- **Forms**:
  - Focus: transition the border color, add slight scale or glow
  - Validation: shake on failure, check mark on success, smooth color transitions
- **Toggle switches**: slide and shift color together over 200-300ms
- **Checkboxes and radios**: animate the check mark, add a ripple
- **Like and favorite**: scale plus rotation, particles, a color change

### State changes

- **Show and hide**: fade plus slide instead of an instant cut, at 200-300ms
- **Expand and collapse**: transition height with overflow handled, rotate the disclosure icon
- **Loading**: skeleton screen fades, spinner animation, progress bars
- **Success and error**: color shifts, icon animation, a gentle scale pulse
- **Enable and disable**: opacity transitions, cursor changes

### Navigation and flow

- **Between routes**: crossfade, or carry a shared element over
- **Tabs**: slide the active indicator, fade or slide the panel content
- **Carousels and sliders**: smooth transforms, snap points, momentum feel
- **Scroll**: parallax layers, sticky headers that change state, scroll progress

### Feedback and guidance

- **Hover hints**: tooltip fade-ins, cursor changes, element highlights
- **Drag and drop**: lift with shadow and scale, highlight drop zones, reposition smoothly
- **Copy and paste**: a brief highlight flash on paste, a "copied" confirmation
- **Focus flow**: light the path through a form or multi-step workflow

### Delight

- **Empty states**: gentle floating on illustrations
- **Completions**: confetti, a check mark flourish, a celebration
- **Easter eggs**: hidden interactions waiting to be found
- **Contextual touches**: weather effects, time-of-day themes, seasonal variation

## Craft and Technique

Match technique to job.

### Duration and easing

**How long, by purpose:**

- **100-150ms**: instant feedback — a button press, a toggle
- **200-300ms**: state changes — hover, opening a menu
- **300-500ms**: layout changes — accordions, modals
- **500-800ms**: entrances — page load

**Easing curves — reach for these rather than the CSS defaults:**

```css
/* Natural deceleration; safe defaults */
--ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1);    /* Refined and even */
--ease-out-quint: cubic-bezier(0.22, 1, 0.36, 1);   /* A touch snappier */
--ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);     /* Decisive and confident */

/* Leave these alone — they read as dated */
/* skip bounce:  cubic-bezier(0.34, 1.56, 0.64, 1) */
/* skip elastic: cubic-bezier(0.68, -0.6, 0.32, 1.6) */
```

**Exits should outpace entrances.** Budget roughly 75% of the enter duration.

### When CSS is enough

Simple, declarative motion belongs here:

- `transition` covers state changes
- `@keyframes` covers multi-step sequences
- Animate only `transform` and `opacity` so the GPU carries the work

### When to reach for JavaScript

Complex, interactive motion needs a scripting layer:

- The Web Animations API for programmatic control
- Framer Motion inside React codebases
- GSAP for elaborate sequences

### Keeping it fast

- **Stay on the GPU**: animate `transform` and `opacity`; avoid layout properties
- **`will-change`**: apply sparingly, only for known-expensive animations
- **Cut paint work**: minimize repaints, apply `contain` where it fits
- **Watch the frame rate**: hold 60fps on target devices

### Honoring reduced motion

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

**Practices that spoil the work**

- Making bounce, elastic, or spring motion the default; reserve physical overshoot for interactions and brands where it is deliberate
- Animating layout properties — width, height, top, left — instead of `transform`
- Stretching feedback past 500ms, which just reads as lag
- Adding motion with no reason — every animation owes a "why"
- Skipping `prefers-reduced-motion`, which is an accessibility failure
- Animating everything, until the accumulated motion is exhausting
- Blocking interaction while an animation plays, unless deliberate

## Check the Result

Put the motion through its paces.

- **Holds 60fps**: no jank on the target hardware
- **Reads as natural**: the easing feels organic rather than mechanical
- **Timed right**: not so fast it jars, not so slow it drags
- **Reduced motion honored**: animations switch off or simplify as they should
- **Never blocking**: interaction stays available during and after
- **Earns its place**: the interface is clearer or more delightful for it
- **Fails open**: Content stays visible if JS errors, is disabled, or hasn't run yet. Never leave content at `opacity: 0` whose only route to visible is a JS-added class. Confirm the reveal script parses and runs (a top-level `return` outside a function is a `SyntaxError` that blanks the whole page); wrap observer setup in `try/catch` that reveals everything on failure.

Motion exists to explain and acknowledge, not decorate. Give every animation a reason, stay inside the performance budget, treat accessibility as part of the spec. Done well, nobody notices the animation — the interface just feels right.
