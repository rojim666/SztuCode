---
name: uicraft
description: Create, improve, audit, and polish distinctive production-grade web interfaces, including marketing/landing pages and personal portfolio sites. Use for UI or frontend design, responsive layouts, typography, color, motion, UX copy, accessibility, performance, design-system alignment, onboarding, edge cases, or visual review of HTML/CSS/JavaScript and component-based web applications. Trigger for requests such as 界面设计、前端美化、响应式、动效、配色、排版、设计评审、无障碍、性能优化、设计系统、空状态、落地页/营销页、个人作品集网站和上线打磨. Do not trigger for backend-only work or frontend tasks with no interface-quality concern.
license: Apache-2.0. Derivative work of Impeccable (https://github.com/pbakaus/impeccable) by Paul Bakaus. Files have been modified. See LICENSE for the license text.
---

# UICraft

Create interfaces with a clear design point of view while preserving usability, accessibility, performance, and the project's existing constraints.

## Decision priority

Apply guidance in this order:

1. Follow explicit user requirements and product constraints.
2. Preserve the established brand and design system unless the user asks to change them.
3. Protect task completion, accessibility, content clarity, and performance.
4. Apply UICraft's aesthetic defaults only after the first three priorities are satisfied.

Treat the recommendations in this skill as context-sensitive defaults, not universal style laws.

## Establish design context

Before making high-impact visual decisions, establish:

- target audience and usage context;
- primary jobs and critical user flows;
- brand personality and desired emotional tone;
- technical, accessibility, performance, and browser constraints.

Use context in this order:

1. Use a `Design Context` supplied by the user.
2. Read `.uicraft.md` from the project root when it exists.
3. Inspect README files, design tokens, existing components, and brand assets for explicit evidence.
4. For missing high-impact product or brand information, ask a focused question. For low-risk gaps, state a conservative assumption and continue.

Infer technical constraints and existing patterns from code. Do not invent audiences, brand values, business goals, or user needs from implementation details alone. For first-time setup, read [uicraft-init.md](references/uicraft-init.md).

## Execute a verified UI workflow

For implementation tasks:

1. Inspect the relevant code, framework, reusable components, tokens, and existing tests.
2. Run or preview the current interface when practical and capture a baseline before substantial visual changes.
3. Select one primary workflow reference and only the supporting foundation references needed for the task.
4. Implement the smallest coherent change that fulfills the request. Preserve existing conventions unless changing them is part of the goal.
5. Verify behavior, visual output, responsive states, keyboard access, reduced motion, loading/error/empty states, and relevant tests.
6. Preview the result after implementation and iterate when the visual result differs from the intended design.
7. Report what changed, what was verified, and any remaining assumptions or untested conditions.

For review-only requests, inspect and report findings without modifying files. Separate measured facts from aesthetic judgment.

When a request spans several concerns, work in this order unless the user specifies otherwise:

1. **Assess** with critique or audit.
2. **Correct structure** with layout, typography, responsive, simplification, or hardening workflows.
3. **Refine expression** with color, motion, intensity, or delight workflows.
4. **Finish and verify** with performance checks and the polish workflow.

Do not stack decorative effects before resolving task flow, hierarchy, accessibility, or structural problems.

## Core design principles

- Choose an intentional direction appropriate to the product; distinctiveness does not require visual intensity.
- Make hierarchy, spacing, typography, and interaction states carry the design before adding decoration.
- Avoid generic patterns when they are merely defaults: undifferentiated card grids, gratuitous glass effects, generic gradient text, decorative glow, or interchangeable dashboard layouts.
- Treat the absence of an explicit brand or design-system constraint as room to make a deliberate choice, not license to default to the most common convention in the product category (e.g., a blue SaaS accent color, or a "Most Popular" badge floating above the middle pricing card as the only way to spotlight a featured tier). A competently executed but conventional result is a missed opportunity when nothing was actually constraining it — when context is weak, pick a specific point of view and justify it, rather than reaching for the category median by default.
- Keep unfamiliar choices explainable in terms of user goals, brand, hierarchy, or interaction feedback.
- Prefer native semantics, progressive enhancement, feature detection, and graceful fallbacks.
- Measure accessibility and performance claims; do not rely on visual inspection alone.
- Follow the user's language for user-facing copy and explanations.

## Select workflow references

Choose one primary workflow. Add supporting references only when they materially help.

### Visual direction

| Need | Primary workflow | Supporting reference |
|---|---|---|
| Increase impact or personality | [bolder.md](references/bolder.md) | typography, spatial design, color |
| Reduce visual intensity | [quieter.md](references/quieter.md) | color, motion, cognitive load |
| Add purposeful color | [colorize.md](references/colorize.md) | color and contrast |
| Build ambitious visual effects | [overdrive.md](references/overdrive.md) | motion, performance, accessibility |

### Layout, type, and adaptation

| Need | Primary workflow | Supporting reference |
|---|---|---|
| Improve layout and spacing | [arrange.md](references/arrange.md) | [spatial-design.md](references/spatial-design.md) |
| Improve typography | [typeset.md](references/typeset.md) | [typography.md](references/typography.md) |
| Adapt across devices or contexts | [adapt.md](references/adapt.md) | [responsive-design.md](references/responsive-design.md) |

### Page types

| Need | Primary workflow | Supporting reference |
|---|---|---|
| Design a marketing/landing page | [landing-page.md](references/landing-page.md) | bolder, typography, color, motion |
| Design a personal portfolio/resume site | [portfolio.md](references/portfolio.md) | typography, color, ux-writing |

### Motion and experience

| Need | Primary workflow | Supporting reference |
|---|---|---|
| Add purposeful motion | [animate.md](references/animate.md) | [motion-design.md](references/motion-design.md) |
| Add personality and delight | [delight.md](references/delight.md) | motion, UX writing |
| Improve onboarding or empty states | [onboard.md](references/onboard.md) | UX writing, cognitive load |

### Quality and resilience

| Need | Primary workflow | Supporting reference |
|---|---|---|
| Technical quality review | [audit.md](references/audit.md) | interaction, responsive, performance |
| UX and design critique | [critique.md](references/critique.md) | heuristics, personas, cognitive load |
| Final pre-release pass | [polish.md](references/polish.md) | relevant domain references |
| Edge cases, i18n, and resilience | [harden.md](references/harden.md) | interaction, responsive |
| Frontend performance | [optimize.md](references/optimize.md) | current platform measurements |

### Systems and content

| Need | Primary workflow | Supporting reference |
|---|---|---|
| Extract reusable components or tokens | [extract.md](references/extract.md) | existing design-system conventions |
| Align with an existing design system | [normalize.md](references/normalize.md) | typography, color, spatial design |
| Simplify or remove noise | [distill.md](references/distill.md) | cognitive load, UX writing |
| Improve interface copy | [clarify.md](references/clarify.md) | [ux-writing.md](references/ux-writing.md) |

## Foundation references

- [typography.md](references/typography.md): type hierarchy, pairing, loading, and accessibility.
- [color-and-contrast.md](references/color-and-contrast.md): palettes, contrast, and themes.
- [spatial-design.md](references/spatial-design.md): spacing, grids, containers, and optical adjustment.
- [motion-design.md](references/motion-design.md): timing, easing, performance, and reduced motion.
- [interaction-design.md](references/interaction-design.md): states, focus, keyboard, forms, and overlays.
- [responsive-design.md](references/responsive-design.md): breakpoints, input modes, images, and real-device testing.
- [ux-writing.md](references/ux-writing.md): labels, errors, empty states, and localization.
- [heuristics-scoring.md](references/heuristics-scoring.md): heuristic review and severity guidance.
- [personas.md](references/personas.md): persona-based walkthroughs without invented user claims.
- [cognitive-load.md](references/cognitive-load.md): cognitive-load analysis and simplification.

## Keep standards current

Treat browser-support tables, Core Web Vitals, and accessibility thresholds as time-sensitive. Verify them against current primary sources when they affect implementation or release decisions. Prefer capability detection and measured results over memorized browser-version claims.

## Attribution

UICraft is a derivative work of [Impeccable](https://github.com/pbakaus/impeccable) by Paul Bakaus (Copyright 2025 Paul Bakaus), used under the Apache License 2.0. Files from the upstream project have been modified. Impeccable in turn is based on Anthropic's `frontend-design` skill.

See [LICENSE](LICENSE) for the license text. UICraft is not endorsed by or affiliated with the Impeccable project or its authors.
