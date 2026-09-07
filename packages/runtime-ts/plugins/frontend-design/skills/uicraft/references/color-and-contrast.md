---
name: Color & Contrast
description: Designing a color system in OKLCH, contrast ratios under WCAG and APCA, deriving a dark-mode palette, and using color accessibly.
---

## Contents

- [Work In OKLCH](#work-in-oklch)
- [Assembling A Working Palette](#assembling-a-working-palette)
- [Contrast And Accessibility](#contrast-and-accessibility)
- [Light And Dark Themes](#light-and-dark-themes)
- [Transparency Is A Warning Sign](#transparency-is-a-warning-sign)


# Color Systems And Contrast

## Work In OKLCH

Retire HSL and author in OKLCH (or LCH). The reason is perceptual uniformity: a fixed step in lightness reads as the same step to the eye. HSL cannot promise that — yellow at 50% lightness looks bright while blue at the same 50% looks dark.

```css
/* OKLCH channels: lightness (0-100%), chroma (0-0.4+), hue (0-360) */
--brand: oklch(60% 0.15 250);       /* Blue */
--brand-soft: oklch(85% 0.08 250);  /* Lighter, hue untouched */
--brand-deep: oklch(35% 0.12 250);  /* Darker, hue untouched */
```

**The part people get wrong**: chroma has to come down as a color approaches white or black. Saturation held high at the extremes of lightness turns garish. Take that blue to 85% lightness and it wants roughly 0.08 chroma — not the 0.15 the base color carries.

## Assembling A Working Palette

### Neutrals Should Not Be Neutral

A flat gray has no character. Push a trace of the brand hue through every neutral instead:

```css
/* Lifeless */
--neutral-100: oklch(95% 0 0);     /* Nothing distinguishes it */
--neutral-900: oklch(15% 0 0);

/* Warm cast — inherits brand warmth */
--neutral-100: oklch(95% 0.01 60);  /* A trace of warmth */
--neutral-900: oklch(15% 0.01 60);

/* Cool cast — technical, professional */
--neutral-100: oklch(95% 0.01 250); /* A trace of blue */
--neutral-900: oklch(15% 0.01 250);
```

At 0.01 the chroma is almost nothing, yet the eye registers it. That trace is what quietly binds the interface to the brand color.

### Roles In A Complete System

| Role | What it covers | Scope |
|------|----------------|-------|
| **Primary** | Brand, CTAs, the actions that matter | one color, 3-5 shades |
| **Neutral** | Text, backgrounds, borders | a scale of 9-11 shades |
| **Semantic** | Success, error, warning, info | four colors, 2-3 shades apiece |
| **Surface** | Cards, modals, and overlays | 2-3 levels of elevation |

Leave secondary and tertiary colors out until something genuinely demands them. A single accent carries most products; every extra one adds a decision to make and more noise on screen.

### Reading 60-30-10 Correctly

The ratio describes **visual weight**, not how many pixels each color occupies:

- **60%** — neutral backgrounds, empty space, base surfaces
- **30%** — supporting colors: text, borders, inactive states
- **10%** — the accent: CTAs, highlights, focus states

The usual failure is spraying the accent everywhere on the grounds that it *is* the brand. Accents earn their pull from scarcity; spend them freely and they stop working.

## Contrast And Accessibility

### What WCAG Requires

| What is being rendered | AA floor | AAA goal |
|------------------------|----------|----------|
| Body copy | 4.5:1 | 7:1 |
| Large type (18pt / about 24 CSS px, or bold 14pt / about 18.7 CSS px) | 3:1 | 4.5:1 |
| Interface controls and icons | 3:1 | 4.5:1 |
| Decoration carrying no meaning | None | None |

**Easy to overlook**: 4.5:1 applies to placeholder text as well. The pale gray placeholder that appears in nearly every form usually falls short.

### Pairings That Fail

Each of these tends to break contrast or simply read poorly:

- pale gray type on white — the most frequent accessibility failure there is
- **gray type over any colored surface** — it goes washed out and lifeless there; darken a shade of the background color instead, or use transparency
- red on green, or green on red — roughly 8% of men cannot tell them apart
- blue on red, which visually vibrates
- yellow on white, which almost never passes
- thin, light type over imagery, where the contrast varies unpredictably

### Pure Gray And Pure Black Are Rarely Deliberate

A tinted neutral usually sits more comfortably inside a brand palette than default gray or black does. Reach for genuinely pure neutrals when contrast, brand, or the content itself calls for them — and never let a tint compromise accessibility.

### Verify With Tools

Your eyes are not a measuring instrument:

- [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
- Your browser's DevTools, under Rendering → Emulate vision deficiencies
- [Polypane](https://polypane.app/) when you want to check as you work

## Light And Dark Themes

### Dark Mode Is Not A Flipped Light Mode

Swapping the values gets you nowhere; the dark theme needs decisions of its own:

| In light mode | In dark mode |
|---------------|--------------|
| Depth comes from shadows | Depth comes from lighter surfaces, shadows drop away |
| Dark text on light | Light text on dark, with weight dialed back |
| Vibrant accents | Accents pulled down a little in saturation |
| White backgrounds | Dark gray around oklch 12-18%, never pure black |

```css
/* Elevation expressed as surface color rather than shadow */
:root[data-theme="dark"] {
  --layer-1: oklch(15% 0.01 250);
  --layer-2: oklch(20% 0.01 250);  /* Higher up reads lighter */
  --layer-3: oklch(25% 0.01 250);

  /* Ease off the text weight */
  --text-weight: 350;  /* Rather than 400 */
}
```

### Two Layers Of Tokens

Keep primitives (`--blue-500`) separate from semantics (`--action-color: var(--blue-500)`). Switching to dark mode means reassigning the semantic layer only; the primitives never move.

## Transparency Is A Warning Sign

Leaning on `rgba` and `hsla` is usually a symptom of a palette with holes in it. Alpha makes contrast unpredictable, costs something at render time, and drifts out of consistency across contexts. Name an explicit overlay color for each context instead. The exception worth keeping is focus rings and interactive states, where seeing through the layer is the point.

---

**Steer clear of**: leaning on color as the only carrier of meaning; building a palette where no color has a defined role; filling large areas with pure black (#000); shipping without testing for color blindness, which affects 8% of men.
