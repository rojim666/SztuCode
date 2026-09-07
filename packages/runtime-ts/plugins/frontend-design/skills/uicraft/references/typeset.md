---
name: typeset
description: Repairs typography — font choices, hierarchy, sizing, weight, and readability — so text stops looking like a default and starts looking deliberate. Use when the user mentions fonts, type, readability, text hierarchy, sizing looks off, or wants more polished, intentional typography.
---

## Contents

- [MANDATORY PREPARATION](#mandatory-preparation)
- [Audit the Current Type](#audit-the-current-type)
- [Draft the Type Plan](#draft-the-type-plan)
- [Rework the Type](#rework-the-type)
- [Final Checks](#final-checks)


Take typography that reads as generic, inconsistent, or structurally vague and rebuild it into type that looks chosen rather than inherited.

## MANDATORY PREPARATION

Before proceeding, apply the main SKILL.md priorities. Use Design Context from the current instructions or `.uicraft.md` when available. If high-impact product or brand context is still missing, read [uicraft-init.md](uicraft-init.md) and ask only focused questions; otherwise state conservative assumptions and continue.

---

## Audit the Current Type

Work out what makes the existing type feel weak or anonymous.

1. **The faces themselves**:
   - Has the project simply taken whatever was default — Inter, Roboto, Arial, Open Sans, the system stack?
   - Does the face carry the brand's personality? A corporate typeface on a playful brand is a mismatch.
   - How many families are in play? Beyond two or three it is nearly always chaos.

2. **Hierarchy**:
   - Is heading, body, and caption obvious at a glance?
   - Do the sizes sit too close to each other? A 14px / 15px / 16px spread produces mush.
   - Is the weight contrast actually visible? Medium next to Regular barely registers.

3. **Scale and sizing**:
   - Do the sizes follow a scale, or were they picked one at a time?
   - Is body copy at a genuinely readable size — 16px or more?
   - Does the sizing approach suit the surface? Fixed `rem` steps for application UI; fluid `clamp()` for headings on marketing and content pages.

4. **Readability**:
   - Are the measures comfortable? 45-75 characters per line is the target.
   - Does the line-height suit this particular face and this particular context?
   - Is there sufficient contrast between the text and what sits behind it?

5. **Consistency**:
   - Does the same kind of element get the same treatment everywhere?
   - Are weights applied to roles consistently — not bold here and semibold there for the identical job?
   - Was letter-spacing decided on, or just left at whatever the browser gave you?

**CRITICAL**: This is not an exercise in making text look fancier. Aim for clearer, more legible, more deliberate. Typography that works goes unnoticed; typography that fails pulls attention away from the content.

## Draft the Type Plan

Consult the [typography reference](typography.md) in this skill for detailed guidance on scales, pairing, and loading strategies.

Then commit to a plan covering:

- **Which faces**: do any need replacing, and what would suit the brand and the context?
- **The scale**: a modular progression — 1.25 is a reasonable ratio — with the levels clearly separated
- **Weights and their jobs**: Regular for running text, Semibold for labels, Bold for headings, or whatever mapping the design calls for
- **Vertical and horizontal rhythm**: line-heights, letter-spacing, and the space between typographic elements

## Rework the Type

### Choosing Faces

When replacement is warranted:
- Let the face express the brand's personality
- If pairing, pair with real contrast — serif beside sans, geometric beside humanist — otherwise stay in one family and vary the weight
- Keep webfont loading from shifting the layout, via `font-display: swap` and metric-matched fallbacks

### Setting Up Hierarchy

Construct a scale you can rely on:
- **Five steps handle almost everything**: caption, secondary, body, subheading, heading
- **Keep one ratio between steps** — 1.25, 1.333, or 1.5
- **Stack the signals**: size plus weight plus color plus space; size by itself is not enough
- **Application UI**: fix the scale in `rem`, nudging it at one or two breakpoints if needed. Fluid sizing works against the spatial predictability that dense, container-driven layouts depend on
- **Marketing and content pages**: let headings and display text flex with `clamp(min, preferred, max)`, while body copy stays fixed

### Repairing Readability

- Cap the measure with `ch` units on the text container — `max-width: 65ch`
- Tune line-height to the role: tight for headings at 1.1-1.2, open for body at 1.5-1.7
- Give light text on dark backgrounds a little extra line-height
- Never let body copy drop below 16px / 1rem

### Detail Work

- Switch on `tabular-nums` wherever figures need to line up in columns
- Handle `letter-spacing` deliberately: open it slightly for uppercase and small caps, leave it default or slightly tight on large display sizes
- Name tokens for their role (`--text-body`, `--text-heading`) instead of their value (`--font-16`)
- Turn on `font-kerning: normal`, and use OpenType features where they earn their place

### Keeping Weights Honest

- Assign every weight a defined role and hold to it
- Three or four weights is plenty — Regular, Medium, Semibold, Bold covers it
- Ship only the weights that are genuinely used; each one costs page weight

Steer clear of these entirely: running more than two or three families; choosing sizes by feel instead of committing to a scale; body text under 16px; display or decorative faces used for running text; blocking zoom with `user-scalable=no`; sizing type in `px` when `rem` is what respects the user's own settings; falling back on Inter, Roboto, or Open Sans in a place where personality is the point; and pairing two faces so alike that the contrast never lands, such as two geometric sans-serifs.

## Final Checks

- **Hierarchy**: is heading versus body versus caption readable instantly?
- **Readability**: does a long passage stay comfortable to the end?
- **Consistency**: do elements sharing a role look identical across the interface?
- **Personality**: does the type communicate the brand?
- **Performance**: do webfonts arrive efficiently and without shifting the layout?
- **Accessibility**: are WCAG contrast ratios met, and does the text survive a zoom to 200%?

Type does more work than any other layer of an interface — nearly all the information travels through it. That makes typography the single highest-leverage thing you can fix.
