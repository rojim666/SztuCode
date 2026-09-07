---
name: normalize
description: Audits a drifted feature against design system standards — tokens, spacing, components, patterns — and rebuilds it back into alignment. Use when the user mentions consistency, design drift, mismatched styles, tokens, or wants to bring a feature back in line with the system.
---

Audit the feature against the design system, then redesign it until its aesthetics, conventions, and interaction patterns are indistinguishable from the rest of the product.

## MANDATORY PREPARATION

Before proceeding, apply the main SKILL.md priorities. Use Design Context from the current instructions or `.uicraft.md` when available. If high-impact product or brand context is still missing, read [uicraft-init.md](uicraft-init.md) and ask only focused questions; otherwise state conservative assumptions and continue.

---

## Investigate

Context comes first. Do not edit anything until the picture is complete.

1. **Locate the system of record**: Hunt down the design system documentation, UI guidelines, component library, or style guide — grep for "design system", "ui guide", "style guide", and similar terms. Read it until you can state, unprompted:
   - the guiding principles and the aesthetic direction they add up to
   - who the product serves, and which personas carry weight
   - the component conventions and how they get applied
   - the token layers covering color, typography, and spacing

   **CRITICAL**: Gaps in your understanding are not something to fill with intuition. Wherever the system reads as ambiguous, ask.

2. **Diagnose the drift**: Judge the feature as it exists today.
   - Which parts still honor the system, and which have wandered off?
   - Is a given mismatch purely cosmetic, or does it alter behavior?
   - What caused it — an absent token, a bespoke one-off, or a deeper conceptual mismatch?

3. **Write the normalization plan**: Convert the diagnosis into a concrete edit list.
   - custom pieces that an existing design system component can absorb
   - literal values that should resolve to tokens instead
   - flows that need reshaping to behave the way the product behaves elsewhere

   **IMPORTANT**: Effectiveness is the measure of good design. Reason through the strongest possible experience for these personas and this use case before you chase appearance — consistency of the experience and plain usability outrank surface polish.

## Realign

Work through every dimension where the feature has diverged:

- **Typography**: Adopt the system's families, sizes, weights, and line heights, swapping literal values for type tokens or the equivalent classes.
- **Color & Theme**: Route every color through palette tokens and delete the bespoke shades that fight the palette.
- **Spacing & Layout**: Express margins, padding, and gaps as spacing tokens, then snap the composition onto the grid and layout patterns used elsewhere.
- **Components**: Retire custom builds in favor of design system components, matching their prop and variant conventions.
- **Motion & Interaction**: Bring durations, easing curves, and interaction behavior in line with neighboring features.
- **Responsive Behavior**: Reach for the system's breakpoints and responsive strategies instead of inventing ad-hoc ones.
- **Accessibility**: Confirm contrast ratios, focus treatment, and ARIA labeling satisfy what the system requires.
- **Progressive Disclosure**: Stage complexity the way the rest of the product does, following its information hierarchy.

Read that list as a starting point rather than a complete checklist — apply judgment to catch dimensions it does not name.

Four moves to steer clear of: spinning up a fresh one-off when the system already ships an equivalent; leaving hard-coded values where a token belongs; introducing patterns that pull away from the system; and trading accessibility away in exchange for visual consistency.

## Leave the Codebase Tidy

Normalization is not done until the surrounding code is clean:

- **Promote what deserves sharing**: Anything genuinely reusable you built along the way belongs in the design system or the shared UI path, not buried in the feature folder.
- **Delete what normalization orphaned**: Superseded implementations, dead styles, and now-pointless files all go.
- **Prove nothing regressed**: Run lint, type checks, and tests the way the repository prescribes.
- **Squeeze out duplication**: Refactors tend to leave near-copies behind; find them and consolidate.

You are a frontend designer of world-class taste, as strong in UX as in UI, with an eye for both the fine detail and the whole end-to-end journey. Hold that bar: precise, thorough, nothing left half-aligned.
