---
name: landing-page
description: Design and build marketing/landing pages — product launches, SaaS marketing sites, campaign pages, and single-page pitches. Use when the user asks for a landing page, marketing site, product launch page, or campaign/pitch page.
---

## Contents

- [MANDATORY PREPARATION](#mandatory-preparation)
- [What Makes a Landing Page Different](#what-makes-a-landing-page-different)
- [Structural Anatomy](#structural-anatomy)
- [Choose a Style Direction](#choose-a-style-direction)
- [Landing-Page Anti-Patterns](#landing-page-anti-patterns)
- [Conversion & UX Considerations](#conversion-ux-considerations)
- [Verify](#verify)

A landing page has one job: move a specific visitor from curiosity to a single action. Everything on the page should serve that one action — clarity and persuasion outrank decorative variety.

## MANDATORY PREPARATION

Before proceeding, apply the main SKILL.md priorities. Use Design Context from the current instructions or `.uicraft.md` when available. If high-impact product or brand context is still missing, read [uicraft-init.md](uicraft-init.md) and ask only focused questions; otherwise state conservative assumptions and continue. Additionally establish: the single primary action (signup, demo request, purchase, waitlist, download), and who is landing on the page (cold traffic vs. warm/referred).

---

## What Makes a Landing Page Different

- **One primary action, stated repeatedly, worded consistently.** Secondary actions (docs, pricing, demo video) exist to remove objections to the primary action, not to compete with it.
- **The page argues a case.** Order sections like a persuasive argument: claim (hero) → proof (social proof, results) → mechanism (how it works, features) → risk reversal (pricing clarity, guarantees, FAQ) → close (final CTA). Don't just list features in arbitrary order.
- **Above-the-fold must answer three questions in under 5 seconds**: what is this, who is it for, why should I care. If a visitor can't answer these from the hero alone, the hero has failed regardless of how polished it looks.
- **Scroll depth is earned, not assumed.** Each section must justify the next scroll — cold traffic abandons pages that get boring or vague.

## Structural Anatomy

Treat this as a checklist of things to *consider*, not a mandatory template to fill in order. Omit sections that don't serve the specific product or audience.

- **Hero**: value proposition, one primary CTA, supporting visual (product shot, illustration, or short demo) — not a generic abstract blob.
- **Social proof band**: logos, user counts, or a single strong quote — placed early if credibility is the biggest objection, later if the product itself is the draw.
- **Feature/benefit sections**: translate features into outcomes; vary the visual treatment section to section (see Anti-Patterns) rather than repeating one card format.
- **How it works**: for products with any onboarding friction, a short numbered walkthrough reduces perceived complexity.
- **Testimonials/case studies**: specific, attributed, ideally with a measurable outcome — generic praise ("Great product!") is worse than omitting testimonials.
- **Pricing or next-step clarity**: even without full pricing, remove ambiguity about what happens after the CTA is clicked.
- **FAQ**: address the actual top objections for this audience, not generic filler questions.
- **Final CTA**: restate the value proposition in one sentence, repeat the primary action.
- **Footer**: legal, secondary navigation, contact — deliberately low-emphasis.

## Choose a Style Direction

Pick one direction deliberately and commit — don't blend all three. The direction should match the product's actual personality and audience, not just whichever looks most impressive.

### 1. Structured Confidence

For enterprise, B2B, fintech, infrastructure, and other contexts where the primary objection is trust and risk, not excitement.

- **Typography**: one high-quality sans (or sans + a single serif for display moments), tight hierarchy, no more than 3 sizes doing real work.
- **Color**: neutral base with a single restrained accent used consistently for every CTA and only for CTAs — resist the pull toward the generic blue/indigo default (see [colorize.md](colorize.md)); a less expected but still credible hue (deep teal, ink navy, warm graphite) reads as more considered.
- **Layout**: grid-driven, generous whitespace, left-aligned content blocks, systematic spacing scale visible throughout.
- **Motion**: minimal — fade/slide entrances only, no scroll-jacking or parallax. Confidence comes from restraint.
- **Signals of quality**: real logos/numbers, specific security/compliance details, precise technical language over marketing adjectives.

### 2. Editorial Momentum

For content tools, creative/consumer products, and brands with a distinct voice, where narrative and personality are part of the pitch.

- **Typography**: an expressive display face (serif or distinctive sans) paired with a quiet body face; large type-scale jumps (not timid 1.2x steps).
- **Color**: one saturated or unusual accent used with intention (not necessarily blue); warm or cool neutrals rather than pure gray.
- **Layout**: asymmetric grids, section-to-section rhythm variation, pull quotes and large numerals used as graphic elements, not just data.
- **Motion**: scroll-triggered reveals with a consistent easing signature; a single hero moment of choreography rather than animation everywhere.
- **Signals of quality**: specific, characterful copy; a clear point of view rather than category-generic claims.

### 3. Kinetic Minimal

For developer tools, technical/AI products, and audiences that read polish as a proxy for product quality.

- **Typography**: a precise sans with a monospace accent used intentionally (code snippets, technical labels, or numeric readouts) — not monospace as a lazy "dev tool" cliché applied everywhere.
- **Color**: dark-mode-first or high-contrast light, one accent reserved for interactive/live elements (cursors, active states, live demo output).
- **Layout**: tight grid, real UI screenshots or live interactive demos rather than illustrations, information density calibrated to a technical audience.
- **Motion**: purposeful micro-interactions tied to real product behavior (typing effects, state transitions, live counters) — motion should demonstrate the product, not just decorate the page.
- **Signals of quality**: real code, real terminal output, real API responses — technical audiences distrust marketing gloss.

## Landing-Page Anti-Patterns

Beyond the general generic-AI tells (see [bolder.md](bolder.md) and [critique.md](critique.md)), watch specifically for:

- Abstract gradient blob or glowing orb behind the hero headline with no relationship to the actual product
- Headline built from interchangeable template language ("The future of X", "Reimagine your Y", "X, reimagined") that could apply to any product in the category
- Three identical icon-in-circle feature cards with one-line descriptions and no visual hierarchy between them
- Testimonial carousel with generic stock-photo avatars and unattributed or vague praise
- A pricing section copied verbatim from the most common SaaS three-tier template (see [arrange.md](arrange.md)'s pricing-tier guidance) when nothing about this product calls for it
- Multiple CTAs with different wording for the same action ("Get Started" / "Try it Free" / "Start Now" scattered across the page) — inconsistent CTA copy adds friction, not variety

## Conversion & UX Considerations

- Mobile hero must work with the CTA visible without excessive scrolling — check real device widths, not just a wide desktop viewport.
- Every CTA should use identical wording for the same action throughout the page; reserve wording variation for genuinely different actions.
- Hero visual assets (video, large images) must not block perceived load — see [optimize.md](optimize.md) for lazy-loading and LCP guidance.
- If the page will be A/B tested or iterated on, keep section boundaries and copy in clearly separable blocks rather than tightly coupling copy to decorative layout.

## Verify

- Can a first-time visitor state what the product is and who it's for after reading only the hero?
- Is there exactly one primary action, worded identically everywhere it appears?
- Does the section order build an argument, or is it an arbitrary feature list?
- Does the chosen style direction match the audience's actual expectations (a fintech buyer and an indie-hacker audience read polish differently)?
- With JavaScript disabled (or if the reveal script throws), is all hero and body content still visible? Scroll-reveal effects must fail open — never hide content behind `opacity: 0` that only a script can undo (see [motion-design.md](motion-design.md)'s "Reveal Animations Must Fail Open").
- Run the standard [critique.md](critique.md) generic-AI check before shipping.
