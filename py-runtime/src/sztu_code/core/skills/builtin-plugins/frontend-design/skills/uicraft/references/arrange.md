---
name: arrange
description: Rebuild layout, spacing, and visual rhythm — repairing monotonous grids, inconsistent spacing, and hierarchy that fails to register. Use when the user says the layout feels off, or raises spacing issues, visual hierarchy, crowded UI, alignment problems, or wanting better composition.
---

## Contents

- [MANDATORY PREPARATION](#mandatory-preparation)
- [Diagnose the Existing Layout](#diagnose-the-existing-layout)
- [Draw Up the Plan](#draw-up-the-plan)
- [Rework the Layout](#rework-the-layout)
- [Confirm the Improvement](#confirm-the-improvement)


Diagnose spatial design that reads as monotonous, crowded, or structurally soft, then rebuild it into something deliberate and rhythmic instead of generic.

## MANDATORY PREPARATION

Before proceeding, apply the main SKILL.md priorities. Use Design Context from the current instructions or `.uicraft.md` when available. If high-impact product or brand context is still missing, read [uicraft-init.md](uicraft-init.md) and ask only focused questions; otherwise state conservative assumptions and continue.

---

## Diagnose the Existing Layout

Work out precisely where the current spatial design falls down.

1. **Spacing**:
   - Do the values come from a system, or were padding and margin picked at random?
   - Is every gap the same size? Uniform padding throughout leaves no rhythm at all.
   - Do related items sit close together while distinct groups get real separation?

2. **Hierarchy**:
   - Run the squint test: defocus your (metaphorical) eyes and check whether the primary element, the secondary element, and the groupings are still readable.
   - Is the hierarchy landing? Space and weight on their own are often sufficient — but is what is currently there doing the job?
   - Does the whitespace steer attention toward what actually matters?

3. **Structure**:
   - Is there an underlying grid, or does the arrangement read as arbitrary?
   - Has the same card grid been applied everywhere — icon, heading, text, repeated without end?
   - Is everything centered? Left alignment with asymmetry usually feels more considered, though treat that as a tendency rather than a law.

4. **Rhythm**:
   - Does the page alternate between tight and generous spacing, or run flat?
   - Is every section built to the same template, producing monotony?
   - Are there deliberate beats of surprise or emphasis anywhere?

5. **Density**:
   - Is it too tight, leaving nothing room to breathe?
   - Is it too loose, with whitespace that serves no purpose?
   - Does the density suit the content? Data-dense interfaces want compression; marketing pages want air.

**CRITICAL**: When an interface feels "off" despite perfectly good color and type, layout is usually the culprit. Treat space as a material you are shaping on purpose.

## Draw Up the Plan

Detailed guidance on grids, rhythm, and container queries lives in the [spatial design reference](spatial-design.md) in this skill.

Settle these four decisions before editing:

- **Spacing system**: commit to one scale. A framework's built-in scale (Tailwind, for instance), rem-based tokens, or something custom all work — consistency counts for more than the particular numbers.
- **Hierarchy strategy**: decide how space will signal what is important.
- **Layout approach**: match the structure to the content — Flex for one dimension, Grid for two, named areas when a page gets complex.
- **Rhythm**: map out where spacing should compress and where it should open up.

## Rework the Layout

### Lock down a spacing scale

- Draw every value from a defined set — a framework scale, rem-based tokens, or a custom scale all qualify. What disqualifies a value is being invented on the spot.
- With custom properties, name by meaning: `--space-xs` through `--space-xl` rather than `--spacing-8`
- Space siblings with `gap` rather than margins, which retires the margin-collapse workarounds
- Reach for `clamp()` when spacing should open up on larger screens

### Build a rhythm

- **Pull related elements close** — roughly 8-12px between siblings
- **Push distinct sections apart** — 48-96px does the separating
- **Vary the gaps inside a section**; identical spacing on every row flattens it
- **Go asymmetric** where it serves the content, instead of defaulting to centered blocks

### Pick the right layout primitive

- **Flexbox handles one dimension**: rows of items, nav bars, button groups, the inside of a card, most component internals. For the bulk of layout work it is both simpler and the better fit.
- **Grid handles two dimensions**: page-level scaffolding, dashboards, data-dense screens, anywhere rows and columns must be controlled together.
- **Resist reaching for Grid first** when Flexbox plus `flex-wrap` would be simpler and bend more easily.
- `repeat(auto-fit, minmax(280px, 1fr))` gives you a responsive grid with no breakpoints involved.
- For complex pages, define the structure with named areas via `grid-template-areas`, and redefine those areas at each breakpoint.

### Break out of card-grid monotony

- Stop treating card grids as the default container — spacing and alignment already group things visually
- Reserve cards for content that is genuinely separate and actionable, and never place a card inside another card
- Disrupt the repetition: change card sizes, let some span extra columns, or interleave non-card content

### Avoid the Default Pricing-Tier Template

When arranging tiered/comparison cards (pricing, plans, packages) without an explicit brand system dictating otherwise, resist collapsing to the most common template: three equal-width cards, a blue/indigo accent, a "Most Popular" pill floating above the middle card, and a bullet checklist. That combination is recognizable as the generic default precisely because it requires no design decision.

- Differentiate the featured tier structurally, not just with a label: an inverted/tinted card background, a distinct typographic treatment for its price, or a deliberate size or elevation difference — a badge alone is the weakest possible signal.
- Choose an accent hue that reflects the product's actual personality rather than reaching for blue because it reads as "professional" by convention.
- A badge or pill can still be part of the solution, but it should reinforce a structural difference already visible in the layout — not substitute for one.

### Sharpen the hierarchy

- Use as few contrast dimensions as the job requires. Space by itself frequently suffices — generous whitespace around an element pulls the eye to it, and some of the most refined work builds its rhythm from space and weight alone. Layer in color or size contrast only once the simpler tools have run out.
- Keep reading flow in mind: in left-to-right languages the eye travels from top-left toward bottom-right, though where the primary action belongs is context-dependent — bottom-right inside a dialog, up top in navigation.
- Let proximity and separation define the content groups.

### Handle depth deliberately

- Define a z-index scale by role: dropdown → sticky → modal-backdrop → modal → toast → tooltip
- Define a matching shadow scale (sm → md → lg → xl) and keep the shadows restrained
- Spend elevation on hierarchy, never on decoration

### Correct by eye when needed

- An icon can be geometrically centered and still look off-center; nudge it when that is clearly the case. Do not make optical corrections on speculation.

**Habits that ruin a layout**

- Reaching for one-off spacing values that live outside the scale
- Spacing everything identically, when it is variation that produces hierarchy
- Boxing every piece of content in a card, as though everything needs a container
- Putting cards inside cards, rather than using spacing and dividers for internal hierarchy
- Repeating the same card grid — icon, heading, text — across the whole interface
- Centering everything, when left alignment with asymmetry reads as more designed
- Falling back on the hero metric layout (big number, small label, stats, gradient) as a template. A prominent metric is fine when it reports genuine user data; it is not fine when the number is decorative.
- Defaulting to CSS Grid where Flexbox would do — reach for the simplest tool that solves it
- Dropping in arbitrary z-index values like 999 or 9999 instead of using a semantic scale

## Confirm the Improvement

- **Squint test**: with vision blurred, do primary, secondary, and the groupings still separate cleanly?
- **Rhythm**: does the page move between tight and generous spacing in a way that feels intentional?
- **Hierarchy**: is the most important content unmistakable inside two seconds?
- **Breathing room**: does it sit comfortably rather than cramped or wastefully empty?
- **Consistency**: is the one spacing system applied everywhere?
- **Responsiveness**: does the composition survive the full range of screen sizes?

Space remains the design tool teams reach for least. Get the rhythm and the hierarchy right and even plain content will look deliberate and finished.
