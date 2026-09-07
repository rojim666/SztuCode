---
name: colorize
description: Brings deliberate color into features that read as flat, gray, or visually inert, so the interface feels warmer and more expressive. Use when the user says the design looks gray or dull, lacks warmth, needs more color, or should feel more vibrant and expressive.
---

## Contents

- [Required Context](#required-context)
- [Read the Current Palette](#read-the-current-palette)
- [Set the Palette Plan](#set-the-palette-plan)
- [Apply Color Where It Earns Its Place](#apply-color-where-it-earns-its-place)
- [Keep It Balanced](#keep-it-balanced)
- [Confirm the Result](#confirm-the-result)


Bring color into work that has gone monochrome, gray, or emotionally flat — deliberately, not decoratively.

## Required Context

Work from the priorities in the main SKILL.md. Take Design Context from the current instructions, or from `.uicraft.md` when the project provides one. If product or brand context that would change your choices is still missing, read [uicraft-init.md](uicraft-init.md) and ask a small number of pointed questions; otherwise declare conservative assumptions and proceed. One additional input is essential here: any brand colors that already exist.

---

## Read the Current Palette

Survey what is there before adding anything.

**Where the design stands today:**

- **How colorless is it?** Fully grayscale, a thin band of neutrals, or a single timid accent?
- **What is being left on the table?** Locate the places where color could carry meaning, sharpen hierarchy, or produce a moment of delight.
- **What suits this product?** Domain and audience both constrain the answer.
- **What already belongs to the brand?** Existing brand colors take precedence over invention.

**What color can actually do for you:**

- **Carry meaning** — green reads as success, red as error, yellow or orange as warning, blue as information
- **Rank things** — pull the eye toward whatever matters most
- **Sort things** — separate sections, types, or states from one another
- **Set a mood** — warmth, energy, trust, creativity
- **Orient people** — help users read the structure and find their way through it
- **Add charm** — small bursts of visual interest and personality

Anything you cannot infer from the codebase is worth asking the user about outright.

**CRITICAL**: A larger palette is not a better one. Color chosen with intent will always beat color sprayed everywhere, and each hue you introduce should be justifiable.

## Set the Palette Plan

Decide the shape of the palette before writing any values:

- **The palette itself**: which hues suit the brand and the context — cap it at 2-4 beyond your neutrals
- **The dominant hue**: which color carries 60% of the colored surface area
- **The supporting hues**: which provide contrast and emphasis, at 30% and 10%
- **The mapping**: exactly where each color shows up, and the reason it is there

**IMPORTANT**: Color exists to reinforce hierarchy and meaning, not to add noise. Where color counts most, using less of it counts for more.

## Apply Color Where It Earns Its Place

Move through these dimensions in turn.

### Meaningful Color

- **State signals**:
  - Success: greens — emerald, forest, mint
  - Error: reds and pinks — rose, crimson, coral
  - Warning: oranges and ambers
  - Info: blues — sky, ocean, indigo
  - Inactive: grays and slates
- **Status badges**: tinted fills or outlines marking active, pending, completed, and the rest
- **Progress**: bars, rings, and charts colored to convey completion or health

### Accents in Action

- **Primary actions**: give the leading buttons and CTAs the color
- **Links**: tint clickable text, keeping accessibility intact
- **Icons**: color the ones that aid recognition or carry personality
- **Headings and key labels**: bring color to section titles
- **Hover**: let color arrive on interaction

### Backgrounds and Surfaces

- **Tinted grounds**: retire flat gray such as `#f5f5f5` in favor of a warm neutral like `oklch(97% 0.01 60)` or a cool one like `oklch(97% 0.01 250)`
- **Zoned sections**: quiet background colors to demarcate regions
- **Gradient grounds**: depth through restrained, deliberate gradients — not the stock purple-into-blue
- **Cards**: a slight tint on card surfaces reads as warmth

**Work in OKLCH.** Because it is perceptually uniform, equal jumps in lightness genuinely *appear* equal, which makes it the right tool for generating scales that hang together.

### Data Visualization

- **Charts and graphs**: let color encode category or magnitude
- **Heatmaps**: intensity standing in for density or importance
- **Comparisons**: distinct colors per dataset or per timeframe

### Edges and Details

- **Accent rules**: a colored border along the left or top edge of a card or section
- **Underlines**: color underlines marking emphasis or an active item
- **Dividers**: swap gray rules for softly colored ones
- **Focus rings**: focus indicators tinted to match the brand

### Color in Type

- **Headings**: brand color on section headings, contrast preserved
- **Emphasis**: color to highlight or to signal category
- **Labels and tags**: compact colored chips for metadata or grouping

### Ornament

- **Illustrations**: colored illustration and icon work
- **Shapes**: geometric forms in brand colors sitting behind the content
- **Gradients**: gradient overlays or mesh backgrounds
- **Organic forms**: soft colored blobs for visual interest

## Keep It Balanced

Color should lift the design, not swamp it.

### Hold the Ratios

- **Dominant, 60%**: the primary brand color, or whichever accent dominates
- **Secondary, 30%**: a supporting hue that supplies variety
- **Accent, 10%**: high contrast, saved for the moments that matter
- **Neutrals, whatever remains**: gray, black, and white doing the structural work

### Stay Accessible

- **Contrast**: meet WCAG — 4.5:1 for text and 3:1 for UI components
- **Never color alone**: pair it with an icon, a label, or a pattern
- **Color vision deficiency**: check that red/green pairings still read for everyone

### Stay Coherent

- **One palette**: draw from the defined set rather than picking ad hoc values
- **Fixed meanings**: green means success everywhere it appears, without exception
- **One temperature**: a warm palette stays warm, a cool one stays cool

**Practices to avoid:** running through the whole rainbow, when 2-4 hues beyond neutrals is the budget; scattering color with no semantic logic behind it; setting gray text on a colored surface, which reads as washed out — take a darker shade of that same background hue, or use transparency; treating pure gray as your neutral rather than tinting it faintly warm or cool for sophistication; filling large areas with pure black (`#000`) or pure white (`#fff`); breaking WCAG contrast requirements; letting color be the sole carrier of information, which is an accessibility failure; coloring everything, which cancels the whole effect; falling back on purple-to-blue gradients, the hallmark of generic-AI visuals; and grabbing flat blue or indigo as the "safe" accent simply because it is the SaaS and B2B default — when no brand color has been specified, that is an opening to choose a considered, less predictable hue that still suits the domain, not a license to land on the category median.

## Confirm the Result

Check that the color you added is doing work:

- **Hierarchy**: is attention being steered where it should go?
- **Meaning**: are states and categories easier to read now?
- **Warmth**: does the interface feel more inviting than it did?
- **Accessibility**: does every combination still clear WCAG?
- **Restraint**: is the result balanced, with each color justified?

Color reaches people emotionally, which is exactly why it needs discipline. Use it to warm the interface, direct the eye, encode meaning, and give the product a voice — but let strategy and restraint outrank saturation and variety. Be colorful on purpose.
