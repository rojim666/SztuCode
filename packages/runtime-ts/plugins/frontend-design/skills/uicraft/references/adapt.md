---
name: adapt
description: Rework an interface so it holds up across screen sizes, devices, input methods, and output targets — breakpoints, fluid layout, touch-sized controls. Use on requests about responsive design, mobile layouts, breakpoints, viewport adaptation, or cross-device compatibility.
---

## Contents

- [MANDATORY PREPARATION](#mandatory-preparation)
- [Read the Context Shift](#read-the-context-shift)
- [Choose a Per-Target Strategy](#choose-a-per-target-strategy)
- [Execute the Adaptation](#execute-the-adaptation)
- [Prove It Holds Up](#prove-it-holds-up)


Take a design that works in one setting and make it work in another — different screen, device, platform, or job to be done.

## MANDATORY PREPARATION

Before proceeding, apply the main SKILL.md priorities. Use Design Context from the current instructions or `.uicraft.md` when available. If high-impact product or brand context is still missing, read [uicraft-init.md](uicraft-init.md) and ask only focused questions; otherwise state conservative assumptions and continue. Additionally gather: target platforms/devices and usage contexts.

---

## Read the Context Shift

Be clear on what is moving, and why, before touching anything.

**Where the design came from**

- Original target — desktop web, a native mobile app, something else?
- Assumptions baked in — wide viewport, mouse, fast connection?
- Which parts genuinely work today?

**Where it is headed**

- **Device**: phone, tablet, desktop, TV, watch, paper?
- **Input**: finger, mouse, keyboard, voice, gamepad?
- **Screen**: what dimensions, what resolution, which orientation?
- **Network**: strong wifi, crawling 3G, fully offline?
- **Situation**: in motion or at a desk, two-second glance or sustained reading?
- **Convention**: what has this platform trained its users to expect?

**Where it will break**

- Things that overflow — copy, navigation, feature surface
- Things that stop working — hover states under a fingertip, targets too small to hit
- Things that read as wrong — desktop idioms on a phone, phone idioms on a desktop

**CRITICAL**: This is not a resize job. A new context means rethinking the experience, not rescaling it.

## Choose a Per-Target Strategy

Each destination pulls the design its own way.

### Desktop → Phone

**Layout**

- Collapse multi-column arrangements into one
- Stack vertically what once sat side by side
- Let components run full width instead of holding fixed widths
- Move navigation from the top or side rail to the bottom

**Interaction**

- Prefer 44x44px touch targets where practical; verify current WCAG requirements, spacing exceptions, and platform guidance
- Wire up swipes where they fit — lists, carousels
- Swap dropdowns for bottom sheets
- Design thumbs-first; keep controls within thumb reach
- Enlarge tap areas and space them further apart

**Content**

- Disclose progressively; never dump everything at once
- Lead with primary content; park secondary material in tabs or accordions
- Tighten the copy
- Keep body text at 16px or larger

**Navigation**

- Hamburger menu or bottom bar
- Strip navigational complexity
- Sticky headers to preserve a sense of place
- A back affordance somewhere in the flow

### Tablet: the hybrid case

**Layout**

- Two columns is the sweet spot — not one, not three
- Push secondary content into side panels
- Master-detail arrangements (list plus detail) suit this size
- Adapt to orientation; portrait and landscape differ

**Interaction**

- Assume touch and pointer both in play
- Keep touch targets generous while allowing denser layouts than phone; verify actual input mode and spacing
- Side drawers for navigation
- Multi-column forms where the content supports them

### Phone → Desktop

**Layout**

- Spread into multiple columns; use the horizontal space
- Side navigation stays permanently visible
- Several information panels at once
- Cap width via max-width — nothing stretches across a 4K display

**Interaction**

- Supplementary detail on hover
- Offer keyboard shortcuts
- Add right-click context menus
- Drag and drop where it helps
- Allow multi-select via Shift/Cmd

**Content**

- Front-load more information; progressive disclosure matters less
- Wide data tables become practical here
- Richer visualizations
- More detailed descriptions

### Screen → Print

**Layout**

- Break pages where the content allows
- Drop navigation, footers, and anything interactive
- Assume black and white, or a very limited palette only
- Leave margins wide enough for binding

**Content**

- Restore what was abbreviated — full URLs, expanded sections
- Page numbers plus running headers and footers
- Metadata such as print date and page title
- Charts redrawn in a print-friendly form

### Web → Email

**Layout**

- Cap the width at 600px
- One column, no exceptions
- Inline the CSS; external stylesheets will not survive
- Fall back to table-based layout for email client compatibility

**Interaction**

- Large, unmistakable CTAs — buttons, not text links
- Skip hover states; they cannot be relied on
- Deep-link into the web app for real interactivity

## Execute the Adaptation

Apply the changes methodically.

### Breakpoints

Pick the thresholds deliberately:

- Mobile: 320px-767px
- Tablet: 768px-1023px
- Desktop: 1024px+
- Or content-driven — put a breakpoint wherever the design actually breaks

### Reflowing the layout

- **CSS Grid/Flexbox**: layouts reflow on their own
- **Container Queries**: respond to the container, not the viewport
- **`clamp()`**: fluid scaling between a floor and a ceiling
- **Media queries**: branch the styling per context
- **Display properties**: reveal or suppress per context

### Making it touchable

- Grow hit areas; prefer 44x44px where practical and validate against current accessibility requirements
- Open up the gaps between interactive elements
- Retire anything hover-dependent
- Give touch feedback — ripples, highlights
- Respect thumb zones; the bottom of the screen beats the top for reach

### Adapting content

- Use `display: none` sparingly — hidden assets still download
- Enhance progressively: core content first, extras on larger screens
- Lazy-load off-screen content
- Responsive images via `srcset` and the `picture` element

### Adapting navigation

- Fold complex navigation into a hamburger or drawer on phone
- Bottom bar in mobile app contexts
- Persistent side rail on desktop
- Breadcrumbs on smaller screens for orientation

**IMPORTANT**: Test on real hardware. DevTools emulation is a useful first pass, not the truth.

**Things that undermine an adaptation**

- Stripping core functionality from mobile — if it matters, make it work there
- Equating desktop with a powerful machine; accessibility needs and aging hardware exist
- Letting information architecture diverge between contexts, which disorients users
- Violating what the platform's users expect of it
- Overlooking landscape orientation on phones and tablets
- Applying stock breakpoints blindly instead of letting content dictate them
- Treating desktop as pointer-only when much desktop hardware has a touchscreen

## Prove It Holds Up

Exercise the result across the matrix:

- **Real hardware**: actual phones, tablets, desktops
- **Both orientations**: portrait and landscape
- **Browser spread**: Safari, Chrome, Firefox, Edge
- **OS spread**: iOS, Android, Windows, macOS
- **Every input**: touch, mouse, keyboard
- **The extremes**: a 320px viewport and a 4K display
- **Degraded networks**: run under throttling

Work as a cross-platform design specialist: the experience should feel native wherever it lands while brand and capability stay consistent. Adapt on purpose, then verify on real devices.
