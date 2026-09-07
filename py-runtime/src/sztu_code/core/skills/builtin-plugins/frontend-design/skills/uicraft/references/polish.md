---
name: polish
description: Runs the last-mile quality sweep over alignment, spacing, consistency, and micro-detail before anything ships. Use when the user mentions polish, finishing touches, a pre-launch review, that something looks off, or wanting to take work from good to great.
---

## Contents

- [Non-Negotiable Setup](#non-negotiable-setup)
- [Read the Situation First](#read-the-situation-first)
- [Sweep Dimension by Dimension](#sweep-dimension-by-dimension)
- [Sign-Off Checklist](#sign-off-checklist)
- [Last Look Before Done](#last-look-before-done)


## Non-Negotiable Setup

Start from the priorities laid out in the main SKILL.md. Take Design Context from whatever the current instructions carry, or from `.uicraft.md` if the project has one. When product or brand context that would materially change your decisions is still missing, open [uicraft-init.md](uicraft-init.md) and ask a short, targeted set of questions; if you would rather not stall, state conservative assumptions explicitly and press on. One extra input matters for this pass: the quality bar — throwaway MVP or flagship.

---

What separates shipped work from finished work is a pile of small things. Hunt them down deliberately.

## Read the Situation First

Establish two things before touching a single pixel.

**How done is it?** Confirm the feature works end to end. Note which known issues are deliberate and should survive the pass, marking them with TODOs. Pin down the standard being applied — MVP or flagship — and how much runway is left before launch, because that governs how deep you go.

**Where is the roughness likely to be?** Scan for visual inconsistency, drifting spacing and alignment, interaction states nobody built, copy that contradicts itself across screens, unhandled edge and error cases, and loading or transition moments that stutter.

**CRITICAL**: Polish belongs at the end of the process, never the beginning. Work that is not yet functionally complete is not a polish candidate.

## Sweep Dimension by Dimension

Take the following axes one at a time rather than wandering the UI at random.

### Alignment and Rhythm

- **Grid discipline**: everything resolves cleanly onto the grid
- **Scale-driven gaps**: every gap comes from the spacing scale — no stray 13px values
- **Optical correction**: compensate for visual weight, since icons frequently need an offset to *look* centered
- **Breakpoint parity**: alignment and spacing hold up at every viewport width
- **Baseline snapping**: elements sit on the baseline grid

**How to verify**: switch on a grid overlay and compare; measure gaps in the browser inspector; resize through several viewport widths; and trust your gut about anything that simply reads as wrong.

### Type Detailing

- **Repeatable hierarchy**: equivalent elements share sizes and weights everywhere they appear
- **Measure**: hold body text to 45–75 characters per line
- **Leading**: line height suits the font size and the surrounding context
- **Widows and orphans**: never strand a single word on a final line
- **Hyphenation**: tuned to the language and the column width
- **Kerning**: tighten or loosen letter spacing where it reads badly, headlines most of all
- **Webfont delivery**: no FOUT or FOIT flashes on load

### Color, Contrast, and Tokens

- **Ratios**: every text color clears the WCAG bar
- **Tokens only**: nothing hard-coded — colors resolve through design tokens
- **Every theme**: the result holds in all theme variants
- **Stable semantics**: a given color signals the same idea across the whole product
- **Focus visibility**: focus indicators are perceivable and contrast sufficiently
- **Tinted neutrals**: skip pure gray and pure black; carry a faint tint of roughly 0.01 chroma
- **Text over color**: gray type on a colored surface is off-limits — reach for a shade of the underlying hue or a transparency instead

### State Coverage

Anything interactive owes the user a complete set of states:

- **Default**: the element at rest
- **Hover**: restrained feedback through color, scale, or shadow
- **Focus**: a keyboard focus indicator, which you may only remove if you replace it
- **Active**: acknowledgement of the click or tap
- **Disabled**: unmistakably not operable
- **Loading**: feedback while async work runs
- **Error**: validation or failure
- **Success**: the action landed

**Skip any of these and the interface reads as broken or confusing.**

### Motion and Transitions

- **Transition length**: animate state changes in the 150–300ms range
- **Easing**: settle on ease-out-quart, quint, or expo for natural deceleration; bounce and elastic curves read as dated, so avoid them
- **Frame budget**: hold 60fps by animating transform and opacity only
- **Purpose**: motion should be doing a job, not decorating
- **Opt-out**: honor `prefers-reduced-motion`

### Wording

- **One name per thing**: terminology does not drift between screens
- **Casing rules**: apply Title Case or Sentence case consistently, not interchangeably
- **Mechanics**: no typos, no grammar slips
- **Right length**: neither padded nor clipped to the point of ambiguity
- **Punctuation**: sentences take periods, labels do not — unless every label does

### Iconography and Imagery

- **One family**: icons come from a single set, or at minimum a matching style
- **Sizing**: icon dimensions stay consistent for a given context
- **Optical alignment**: icons line up with neighboring text by eye
- **Alt text**: every image carries a descriptive alternative
- **Reserved space**: aspect ratios are declared so images never shift the layout as they load
- **High-DPI**: 2x assets exist for retina screens

### Form Mechanics

- **Labels**: every input is properly labeled
- **Required markers**: clear, and identical everywhere
- **Error copy**: useful, and phrased consistently
- **Focus order**: tabbing moves through the form in a sensible sequence
- **Auto-focus**: used where it genuinely helps, not by reflex
- **Validation moment**: pick on-blur or on-submit and stick to it

### The Unhappy Paths

- **Async feedback**: no operation runs without a loading signal
- **Empty states**: offer something useful rather than a void
- **Errors**: explain the problem and hand the user a way out
- **Confirmation**: successful actions say so
- **Overflow**: extremely long names and descriptions still render sanely
- **Absent data**: missing values degrade gracefully
- **Offline**: handled sensibly where it applies

### Across Viewports

- **Full range**: exercise mobile, tablet, and desktop
- **Touch targets**: aim for 44x44px on touch devices, and check the current WCAG requirements along with the exceptions they permit
- **Legibility**: nothing below 14px on mobile
- **Horizontal scroll**: content stays inside the viewport
- **Reflow**: the layout rearranges in a way that makes sense

### Speed and Stability

- **First paint**: the critical path is optimized
- **CLS**: nothing jumps once loading finishes
- **Responsiveness**: interactions land without lag or jank
- **Images**: correct formats, correct dimensions
- **Deferred loading**: offscreen content loads lazily

### The Code Itself

- **Debug output**: no console logging left in production
- **Dead code**: commented-out blocks are deleted
- **Imports**: unused dependencies are pruned
- **Naming**: variables and functions follow project convention
- **Types**: no TypeScript `any`, no suppressed errors
- **Semantics**: correct ARIA labeling on top of semantic HTML

## Sign-Off Checklist

Walk the list end to end:

- [ ] Alignment holds at every breakpoint
- [ ] Every gap traces back to a design token
- [ ] Type hierarchy repeats predictably
- [ ] No interactive element is missing a state
- [ ] Every transition runs at 60fps
- [ ] Copy reads consistently and cleanly
- [ ] Icons match in style and size
- [ ] Forms are labeled and validated throughout
- [ ] Error states point toward a fix
- [ ] Loading states communicate clearly
- [ ] Empty states invite rather than dead-end
- [ ] Touch targets satisfy current accessibility requirements and feel comfortable to hit
- [ ] Text contrast clears WCAG AA
- [ ] The whole flow is operable from the keyboard
- [ ] Focus indicators can be seen
- [ ] The console is free of errors and warnings
- [ ] Nothing shifts position after load
- [ ] Every supported browser renders it correctly
- [ ] Reduced-motion preferences are honored
- [ ] The code is tidy — no leftover TODOs, console.logs, or commented blocks

**IMPORTANT**: This is detail work. Zoom in, squint at the screen, and actually use the thing. Small wins compound.

**Things to steer clear of**: polishing something that is not functionally complete; burning hours on refinement when the thing ships in 30 minutes, which calls for triage instead; introducing regressions during the pass, so test as you go; papering over a systemic problem one instance at a time, because spacing that is wrong everywhere is a system fix; and perfecting a single corner while the rest stays rough, since quality should land at one consistent level.

## Last Look Before Done

Run these before you call it finished:

- **Drive it yourself**: interact with the feature rather than reading the diff
- **Real hardware**: DevTools emulation is not a substitute for a device
- **Second pair of eyes**: hand it to someone else, who will spot what you stopped seeing
- **Design comparison**: check it against what was intended
- **Every state**: exercise more than the happy path

You bring world-class attention to detail and exquisite taste to this. Keep refining until the result feels effortless, reads as intentional, and behaves flawlessly. The details are the work.
