---
name: quieter
description: Dials down interfaces that shout — softening intensity and overstimulation while keeping the design sharp. Use when the user mentions too bold, too loud, overwhelming, aggressive, garish, or wants a calmer, more refined aesthetic.
---

Take a design that reads as too bold, aggressive, or overstimulating and lower its visual volume — arriving somewhere more refined and approachable without giving up any effectiveness.

## MANDATORY PREPARATION

Before proceeding, apply the main SKILL.md priorities. Use Design Context from the current instructions or `.uicraft.md` when available. If high-impact product or brand context is still missing, read [uicraft-init.md](uicraft-init.md) and ask only focused questions; otherwise state conservative assumptions and continue.

---

## Diagnose the Noise

Work out precisely where the intensity is coming from.

1. **Trace the sources of loudness**:
   - **Saturation**: colors cranked to full brightness or full chroma
   - **Contrast**: harsh juxtapositions stacked one after another
   - **Weight**: a crowd of heavy, bold elements all shouting at once
   - **Motion**: excessive movement, or effects that are unnecessarily theatrical
   - **Density**: an overload of elements, patterns, and decoration
   - **Uniform scale**: everything sized large, so nothing reads as more important

2. **Frame the situation before touching anything**:
   - What job is this interface doing? A marketing page, a working tool, and a reading surface each tolerate different energy.
   - Who is on the other side of it? Certain audiences genuinely want intensity.
   - What already succeeds here? Good ideas should survive the pass.
   - What is the message at the center? That part gets protected.

Anything you cannot infer from the codebase, put to the user as a direct question.

**CRITICAL**: Quiet is not a synonym for dull or generic. The target is refinement, sophistication, and comfort for the eye — the restraint of a luxury object, never the emptiness of low effort.

## Set the Strategy

Decide how to drop the volume without dropping the impact:

- **Color**: pull saturation down, or move the palette toward more sophisticated hues?
- **Hierarchy**: which handful of elements keep their boldness, and which step back?
- **Subtraction**: what disappears entirely?
- **Restraint as a signal**: where can holding back read as quality?

**IMPORTANT**: Designing quiet is the harder discipline — bold hides imprecision, subtlety does not.

## Turn the Volume Down

Move through each dimension in turn.

### Color

- Ease fully saturated values back to roughly 70-85% saturation
- Trade bright hues for muted, more sophisticated ones
- Work with a smaller set of colors, chosen more deliberately
- Let neutrals carry the surface and reserve color for accent — around the 10% mark
- Spend high contrast only where it genuinely earns attention
- Reach for grays with a warm or cool tint rather than pure gray; the tint adds refinement without adding volume
- Gray text on a colored background is the one combination to rule out — use a deeper shade of the background color, or transparency, instead

### Visual Weight

- **Type**: step weights down (900 becomes 600, 700 becomes 500) and shrink sizes where the role allows
- **Quiet hierarchy**: signal importance with weight, size, and spacing rather than color and boldness
- **Air**: open up breathing room and let density fall
- **Rules and borders**: thin them, fade their opacity, or drop them altogether

### Subtraction

- Strip decoration that serves no purpose — gradients, shadows, patterns, textures
- Calm the geometry: pull back extreme border radii and tame custom shapes
- Collapse unnecessary layering into a flatter arrangement
- Scale back or delete blurs, glows, and stacked shadows

### Motion

- Shrink travel distances (10-20px rather than 40px) and gentle the easing
- Retain motion that does a job; cut the flourishes
- Swap dramatic effects for quiet micro-feedback
- Prefer ease-out-quart for smooth, understated movement — bounce and elastic curves are out
- If an animation has no clear purpose, remove it rather than soften it

### Composition

- Narrow the jumps between sizes; smaller steps read calmer
- Pull stray elements back onto the grid
- Replace wildly varying spacing with a steady, consistent rhythm

Guard against overcorrecting. Flattening everything to one size and weight destroys hierarchy, which still matters. Draining all color is not quiet, it is grayscale. Stripping every trace of personality is not refinement. Interactive elements still need obvious affordances, so usability never gets traded for calm. And a page of uniformly small, light elements has nothing to anchor the eye.

## Check the Result

Confirm the pass improved things rather than merely muting them:

- **Task success**: can people still get what they came for, just as easily?
- **Character**: does it still feel like something, or has it turned generic?
- **Reading comfort**: is longer-form text easier to sit with now?
- **Perceived quality**: does the whole thing read as more considered and more premium?

Quiet design is design that is sure of itself — it has no need to raise its voice. Less really is more, and less is also the harder thing to get right, so refine deliberately and keep every choice intentional.
