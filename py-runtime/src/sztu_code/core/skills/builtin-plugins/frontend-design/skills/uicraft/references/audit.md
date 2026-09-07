---
name: audit
description: Technical quality sweep covering accessibility, performance, theming, responsive behavior, and anti-patterns. Produces a scored report with P0-P3 severities plus a prioritized follow-up plan. Use when the user wants an a11y check, a performance review, or a general implementation-quality assessment.
---

## Contents

- [Before You Start](#before-you-start)
- [Five-Dimension Scan](#five-dimension-scan)
- [Write The Report](#write-the-report)
- [Follow-Up Plan](#follow-up-plan)


## Before You Start

Begin from the priorities set out in the main SKILL.md. Pull Design Context from the current instructions or from `.uicraft.md` whenever either supplies it. If product or brand context that would materially change your verdict is still missing, consult [uicraft-init.md](uicraft-init.md) and ask a small number of targeted questions; when that is not practical, write down conservative assumptions and carry on.

---

This workflow measures the **technical** health of an implementation and reports on it. A review-only request means read, never write. If repairs were requested too, complete the whole audit first, then move into the workflow references that address what surfaced.

Treat the job as a code inspection rather than a critique of taste: report what can be measured or verified in the source.

## Five-Dimension Scan

Sweep five dimensions and score each one from 0 to 4 against the rubric that follows it.

### Dimension 1 — Accessibility (A11y)

**Look for**:
- **Contrast**: text falling under 4.5:1 (under 7:1 where AAA is the target)
- **Semantics and naming**: native HTML first — verify accessible names, roles, and states, and reach for ARIA only where native elements cannot carry the semantics
- **Keyboard operation**: absent focus indicators, tab order that jumps around, traps the user cannot escape
- **Document structure**: broken heading hierarchy, missing landmarks, `div`s doing a button's job
- **Images**: alt text absent or uninformative
- **Forms**: unlabeled inputs, vague error text, no signal for which fields are required

**Rubric**: 0 = unusable, fails WCAG A. 1 = wide gaps, barely any ARIA labels, no keyboard path. 2 = partial effort, significant holes remain. 3 = WCAG AA largely satisfied, small gaps. 4 = WCAG AA fully satisfied and edging toward AAA.

### Dimension 2 — Performance

**Look for**:
- **Layout thrashing**: layout properties read and written back inside loops
- **Costly animation**: width, height, top, or left animated where transform and opacity would do
- **Optimization left on the table**: assets shipped unoptimized, loading priority set wrong, work performed that need not happen, animation bottlenecks you have actually measured
- **Bundle weight**: imports nothing needs, dependencies nothing uses
- **Render behavior**: re-renders that serve no purpose, memoization that should be present and isn't

**Rubric**: 0 = severe, layout thrash and nothing optimized. 1 = major, no lazy loading and expensive animations. 2 = some optimization, gaps remain. 3 = mostly optimized, small wins still available. 4 = fast, lean, thoroughly optimized.

### Dimension 3 — Theming

**Look for**:
- **Literal colors**: values written inline instead of drawn from design tokens
- **Dark mode failures**: variants never defined, or contrast that collapses in the dark theme
- **Token misuse**: the wrong token chosen, or token layers mixed together
- **Switching bugs**: values that refuse to update when the theme flips

**Rubric**: 0 = no theming at all, everything hard-coded. 1 = a handful of tokens over a hard-coded base. 2 = tokens exist but get used inconsistently. 3 = tokens in use with a few stray literals. 4 = complete token system, dark mode flawless.

### Dimension 4 — Responsive Design

**Look for**:
- **Pinned widths**: hard-coded dimensions that collapse on a phone
- **Touch targets**: consult the current WCAG requirements alongside product guidance, and favor generous targets — 44x44px is a sound aim — while accounting for permitted spacing and equivalent-control exceptions
- **Sideways scrolling**: content overflowing at narrow viewports
- **Text scaling**: layouts that come apart once the user enlarges type
- **Absent breakpoints**: no tablet or mobile treatment

**Rubric**: 0 = desktop only, breaks on mobile. 1 = a few breakpoints, many failures. 2 = usable on mobile with rough edges. 3 = responsive, minor target-size or overflow problems. 4 = fluid across viewports with properly sized targets.

### Dimension 5 — Anti-Patterns (CRITICAL)

Audit against every **DON'T** rule stated in this skill. Two families matter: signatures of generic AI output (the telltale AI palette, gradient text, glassmorphism, hero metric slabs, card grids, default fonts), and everyday design mistakes (gray on color, cards nested inside cards, bounce easing, copy that repeats itself).

**Rubric**: 0 = generic patterns dominate. 1 = several loud generic tells. 2 = a few tells a viewer would catch. 3 = mostly deliberate. 4 = distinctive and coherent. Label this score for what it is — a subjective design call, not a measured technical fact.

## Write The Report

### Scorecard

| Dimension | Score | Headline finding |
|-----------|-------|------------------|
| Accessibility | ? | [worst a11y defect, or "--"] |
| Performance | ? | |
| Responsive Design | ? | |
| Theming | ? | |
| Anti-Patterns | ? | |
| **Total** | **??/20** | **[Rating band]** |

**Rating bands**: 18-20 Excellent (polish only), 14-17 Good (shore up the weak dimensions), 10-13 Acceptable (substantial work ahead), 6-9 Poor (needs an overhaul), 0-5 Critical (foundations are wrong).

### Verdict On Anti-Patterns
**Lead with this.** One question, pass or fail: does the work read as AI-generated? Name the specific tells. Do not soften the answer.

### Executive Summary
- Health score: **??/20** ([rating band])
- How many issues turned up, counted by severity: P0/P1/P2/P3
- The three to five that matter most
- What to do next

### Findings, Ranked By Severity

Assign every issue a **P0-P3 severity**:
- **P0 Blocking**: the task cannot be completed — fix now
- **P1 Major**: serious friction, or a WCAG AA violation — fix before shipping
- **P2 Minor**: irritating but workable — fix on the next pass
- **P3 Polish**: no real user impact — fix if the schedule allows

Record each issue with:
- **[P?] A name for the issue**
- **Location**: component, file, line
- **Category**: Accessibility / Performance / Theming / Responsive / Anti-Pattern
- **Impact**: what it does to users
- **WCAG/Standard**: the standard breached, where one applies
- **Recommendation**: the fix
- **Suggested next workflow**: the relevant UICraft workflow plus the exact issue it should take on

### Systemic Patterns

Call out repeat offenders that point to a structural gap rather than an isolated slip:
- "Colors are hard-coded across 15+ components where design tokens belong"
- "Touch targets sit under 44px throughout the mobile experience"

### What Already Works

Name the parts that hold up — good practice worth preserving and repeating elsewhere.

## Follow-Up Plan

Order the recommended workflows by severity, P0 first, then P1, then P2:

1. **[P?] Workflow name** — one line tying it to a specific finding from this audit
2. **[P?] Workflow name** — one line tying it to a specific finding from this audit

**Rules**: every finding maps to whichever workflow in the main SKILL.md fits it best. Suggest a workflow only when an observed issue calls for it. If the user wants fixes applied, let the polish workflow come last, once the higher-severity work is done.

Close the summary by telling the user:

> You can ask me to address these one at a time or implement the prioritized set.
>
> Re-run the UICraft audit after fixes to verify the result.

**IMPORTANT**: thoroughness only counts when it stays actionable. A pile of P3 entries buries the signal — lead with what genuinely matters.

Five habits to steer clear of: logging an issue without saying why it hurts anyone; handing over advice too generic to act on; omitting the positive findings, which deserve their own mention; flattening the priorities so that everything reads as P0; and reporting a problem you never verified.

Your role here is technical quality auditor: document methodically, prioritize without sentiment, point at exact code locations, and leave behind an unambiguous route to a better implementation.
