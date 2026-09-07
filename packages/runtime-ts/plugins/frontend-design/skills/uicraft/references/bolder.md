---
name: bolder
description: Turn up the volume on a design that plays it safe — more presence, more character, more memorability, without giving up usability. Use when the work is called bland, generic, forgettable, or lacking personality, or when someone asks for real visual impact.
---

## Contents

- [MANDATORY PREPARATION](#mandatory-preparation)
- [Diagnose the Flatness](#diagnose-the-flatness)
- [Set the Amplification Strategy](#set-the-amplification-strategy)
- [Turn Up Each Dimension](#turn-up-each-dimension)
- [Check It Held Together](#check-it-held-together)


Take a design that is underpowered, anonymous, or overly cautious, and give it enough presence and character that people remember the experience.

## MANDATORY PREPARATION

Before proceeding, apply the main SKILL.md priorities. Use Design Context from the current instructions or `.uicraft.md` when available. If high-impact product or brand context is still missing, read [uicraft-init.md](uicraft-init.md) and ask only focused questions; otherwise state conservative assumptions and continue.

---

## Diagnose the Flatness

Work out precisely why the current design reads as timid:

1. **Name the source of the weakness**:
   - **Off-the-shelf decisions**: system typefaces, default palette, textbook layout
   - **No range in scale**: every element sits in the same middling size band
   - **Uniform weight**: nothing outweighs anything else visually
   - **No pulse**: zero motion, zero energy
   - **Fully predictable**: familiar patterns delivering no surprise
   - **Level hierarchy**: nothing claims the eye first

2. **Pin down the situation**:
   - Brand personality — how hard is it fair to push?
   - Purpose — a marketing page tolerates far more than a financial dashboard
   - Audience — what will actually land with them?
   - Constraints — brand rules, accessibility, performance budget

Anything you cannot infer from the codebase, put to the user as a direct question.

**CRITICAL**: bolder is not louder-and-messier. It means distinctive, confident, hard to forget. Aim for drama you chose on purpose, never noise that happened by accident.

**WARNING - GENERIC-AI TRAP**: asked to be "bolder", AI reaches for the same worn shortcuts — cyan-to-purple gradients, glassmorphism, neon on dark, gradient-filled metric numbers. Those are the antithesis of bold; they are stock. Go back through every DON'T in this skill first. Bold is distinctiveness, not a heavier coat of effects.

## Set the Amplification Strategy

Decide how the impact will rise without the design losing coherence:

- **Focal point**: choose a single hero moment and make that one exceptional
- **Personality direction**: maximalist chaos, elegant drama, playful energy, dark and moody — commit to one lane
- **Risk budget**: agree how experimental this can get, then push right up to the edge of the constraints
- **Hierarchy amplification**: widen the gap — the large gets larger and the small gets smaller

**IMPORTANT**: a bold interface still has to work. Impact that costs the user function is only decoration.

## Turn Up Each Dimension

Raise the intensity methodically across all of these:

### Type with conviction
- **Retire the default typefaces**: trade system fonts for something with a voice (the typography guidance has starting points)
- **Scale in leaps**: jumps of 3x–5x between levels, not a polite 1.5x
- **Weight extremes**: set 900 against 200 rather than 600 against 400
- **Choices nobody expects**: variable fonts, display faces for headlines, condensed or extended widths, monospace deployed as a deliberate accent rather than a lazy "dev tool" default

### Color that commits
- **Push saturation** toward vivid and energetic, stopping short of neon
- **Unlikely pairings**: build a palette from combinations people do not expect, and stay away from the purple-blue gradient of generic-AI output
- **One color in charge**: allow a single bold hue to occupy roughly 60% of the surface
- **Accents with bite**: high-contrast accent colors that genuinely pop
- **Tint the neutrals**: swap pure gray for gray carrying a hint of the palette
- **Gradients with intent**: multi-stop gradients you designed, not the default purple-to-blue

### Space used dramatically
- **Big leaps in scale**: give the elements that matter 3–5x the size of what surrounds them
- **Break the grid**: let hero elements spill out of containers and cross boundaries
- **Asymmetry**: replace centered, evenly balanced arrangements with compositions that hold tension
- **Lavish emptiness**: think 100–200px of breathing room where the safe version used 20–40px
- **Overlap**: stack elements deliberately to build depth

### Surface and texture
- **Shadows with scale**: large, soft elevation shadows — not the stock drop shadow on a rounded rectangle
- **Treat the background**: mesh patterns, noise, geometric motifs, gradients placed on purpose (again, not purple-to-blue)
- **Depth from material**: grain, halftone, duotone, layering — and NOT glassmorphism, which is thoroughly overused generic-AI
- **Frames and edges**: heavy borders, decorative frames, custom silhouettes, rather than a rounded rectangle wearing one colored edge
- **Bespoke pieces**: illustration, custom iconography, and decorative detail that says something about the brand

### Motion with intent
- **Choreograph the entrance**: stagger page-load animation with 50–100ms offsets between elements
- **Use the scroll**: parallax, reveals, sequences triggered by scroll position
- **Micro-interactions**: hover responses, click feedback, and state changes that feel satisfying
- **Transitions**: make them smooth and clearly perceivable with ease-out-quart, quint, or expo — bounce and elastic just cheapen the result

### Composition that takes risks
- **Hero moments**: give the focal point treatment dramatic enough to be unmistakable
- **Diagonals**: break out of strict horizontal and vertical alignment
- **Full bleed**: run elements to the full width or height of the viewport
- **Proportions off the beaten path**: forget the golden ratio and try a 70/30 or 80/20 split

**Lines not to cross**:
- Piling on effects with no reason behind them — chaos is not boldness
- Trading legibility for looks; body copy stays readable, always
- Making everything loud, which flattens the contrast that boldness depends on
- Letting accessibility slide; WCAG still applies to dramatic work
- Drowning the user in animation, because motion fatigue is real
- Borrowing whatever is trending, since bold means distinctive rather than derivative

## Check It Held Together

Confirm the amplification cost you nothing in usability or coherence:

- **Not generic-AI**: could this be mistaken for any other AI-generated "bold" design? If so, restart.
- **Still functional**: can people finish their tasks without fighting the decoration?
- **Coherent**: does the whole thing read as deliberate and unified?
- **Memorable**: will anyone recall it tomorrow?
- **Performant**: do the effects hold their frame rate?
- **Accessible**: are the accessibility standards still met?

**The acid test**: show it to someone and claim "an AI made this bolder." If they buy it without hesitation, the work has failed. Bold is distinctiveness, not extra AI effects.

Boldness is really confidence made visible — it accepts risk, states a position, and leaves an impression. Strip the strategy out and all that remains is volume. Be deliberate, be dramatic, be impossible to forget.
