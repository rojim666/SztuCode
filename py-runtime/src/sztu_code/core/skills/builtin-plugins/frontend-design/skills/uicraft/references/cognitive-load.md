---
name: Cognitive Load
description: A diagnostic framework for the mental effort an interface demands — separating intrinsic, extraneous, and germane load, then draining the load that earns nothing.
---

## Contents

- [Where the Effort Comes From](#where-the-effort-comes-from)
- [The Four-Item Ceiling](#the-four-item-ceiling)
- [Audit Checklist](#audit-checklist)
- [Recurring Overload Patterns](#recurring-overload-patterns)


# Assessing Cognitive Load

Every interface bills its user in mental effort. When the bill runs too high, people misstep, lose patience, and leave. Use this reference to locate the overload and drain it.

---

## Where the Effort Comes From

Three distinct kinds of load are at play, and each calls for a different response.

### Intrinsic — the cost of the job itself
Some difficulty belongs to the work the user came to do. You cannot delete it, but you can give it shape.

**Give it shape by**:
- Splitting one large task into a sequence of smaller, discrete moves
- Handing over scaffolding: starter templates, sensible defaults, worked examples
- Surfacing only what the current step requires and deferring the rest
- Clustering decisions that naturally belong together

### Extraneous — the cost you invented
Effort that exists purely because of design decisions. It buys nothing, so cut it without mercy.

**Where it usually comes from**:
- Navigation the user must mentally reconstruct before moving anywhere
- Labels vague enough that their meaning has to be guessed
- Clutter, where several elements fight over the same attention
- Patterns that shift between screens, so nothing ever becomes learnable
- Extra hops wedged between the user's intent and the result

### Germane — the cost that pays back
Effort invested in forming a mental model. Keep this one: it converts into mastery.

**Feed it with**:
- Complexity unwrapped in stages instead of all at once
- Repeated patterns, so what was learned once transfers
- Feedback that confirms the user's model was correct
- Onboarding delivered through doing, not through paragraphs to read

---

## The Four-Item Ceiling

**Working memory tops out around four items held simultaneously** (Miller's Law, as revised by Cowan, 2001).

At each decision point, tally the distinct options, actions, and facts the user has to juggle at the same moment:
- **Four or fewer**: inside the limit, workable
- **Five to seven**: at the edge — group them, or defer some behind progressive disclosure
- **Eight or more**: past the limit — expect skipping, misclicks, and abandonment

**Turning the ceiling into concrete caps**:
- Top-level navigation: 5 entries maximum; everything else belongs under named categories
- Form groups: at most 4 fields before a visual break
- Buttons in one view: one primary, one or two secondary, the remainder collapsed into a menu
- Dashboards: no more than 4 headline metrics readable without scrolling
- Pricing plans: 3 at most, since more tips comparison into analysis paralysis

---

## Audit Checklist

Score the interface against these eight questions:

- [ ] **Undivided focus**: Can the primary task be finished without competing elements pulling attention away?
- [ ] **Chunking**: Does information arrive in digestible groups of 4 items or fewer?
- [ ] **Grouping**: Do related items read as a set through proximity, a border, or a shared background?
- [ ] **Visual hierarchy**: Is the most important thing on screen obvious at a glance?
- [ ] **Serial decisions**: Can one decision be settled before the next one arrives?
- [ ] **Minimal choices**: Does any single decision point stay at 4 visible options or fewer?
- [ ] **Working memory**: Must the user carry information forward from an earlier screen to act here?
- [ ] **Progressive disclosure**: Does complexity appear only at the moment it is needed?

**Reading the score**: tally the failures. Zero or one means load is low and the design is in good shape. Two or three is moderate — put the fix on the near-term list. Four or more is a critical overload that needs correcting now.

---

## Recurring Overload Patterns

### 1. The Option Avalanche
**Symptom**: Ten or more choices dumped on screen with nothing ranking them.
**Remedy**: Sort them into categories, mark a recommendation, and hide the tail behind progressive disclosure.

### 2. The Carry-Forward
**Symptom**: Finishing step 3 depends on something the user saw back in step 1.
**Remedy**: Keep that context on screen, or restate it exactly where it is needed.

### 3. The Unmarked Map
**Symptom**: The user has to construct their own model of where everything lives.
**Remedy**: Make current position permanently visible through breadcrumbs, active states, and progress indicators.

### 4. The Vocabulary Toll
**Symptom**: Technical or in-house wording that the user must translate before proceeding.
**Remedy**: Write plainly. Where a domain term genuinely cannot be avoided, define it inline.

### 5. The Flat Signal
**Symptom**: Every element carries identical visual weight, so nothing rises above the rest.
**Remedy**: Build a real hierarchy — a single primary element, 2–3 secondary ones, and everything remaining muted.

### 6. The Shifting Rules
**Symptom**: The same kind of action behaves one way here and another way there.
**Remedy**: Standardize the interaction patterns so that equivalent actions get equivalent UI.

### 7. The Parallel Demand
**Symptom**: The interface expects reading, deciding, and navigating to happen at once.
**Remedy**: Put the steps in sequence and let the user handle one at a time.

### 8. The Scavenger Hunt
**Symptom**: A single decision forces hopping across screens, tabs, or modals to assemble the facts.
**Remedy**: Co-locate everything that decision needs and cut the back-and-forth.
