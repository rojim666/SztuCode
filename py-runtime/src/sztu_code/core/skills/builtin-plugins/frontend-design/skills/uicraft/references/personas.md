---
name: Personas
description: A set of five user archetypes to design-test against — the power user, the first-time visitor, the accessibility-dependent user, the impatient executive, and the non-technical elder.
---

## Contents

- [1. Efficiency-Obsessed Power User — "Alex"](#1-efficiency-obsessed-power-user-alex)
- [2. Disoriented First-Timer — "Jordan"](#2-disoriented-first-timer-jordan)
- [3. Assistive-Tech User — "Sam"](#3-assistive-tech-user-sam)
- [4. Methodical Edge-Case Hunter — "Riley"](#4-methodical-edge-case-hunter-riley)
- [5. Divided-Attention Mobile User — "Casey"](#5-divided-attention-mobile-user-casey)
- [Choosing Which Personas to Run](#choosing-which-personas-to-run)
- [Personas Derived From the Project](#personas-derived-from-the-project)


# Design Testing Through User Archetypes

Run the interface past five separate archetypes rather than judging it from one seat. A lone "design director" viewpoint has blind spots; each archetype below lights up a different category of failure.

**Procedure**: pick the 2–3 archetypes that fit the interface under review, perform the primary user action once in each of their shoes, and write up concrete red flags rather than vague worries.

---

## 1. Efficiency-Obsessed Power User — "Alex"

**Who**: Already fluent in comparable products. Wants throughput, resents being led by the hand. Either uncovers a fast path or walks away.

**Typical behavior**:
- Blows past onboarding and any written instructions
- Hunts for keyboard shortcuts before anything else
- Reaches for multi-select, batch editing, and automation
- Bristles at mandatory steps that serve no visible purpose
- Bails the moment something feels sluggish or condescending

**Probe with**:
- Does the core task finish inside 60 seconds for Alex?
- Do frequent actions have keyboard shortcuts behind them?
- Can onboarding be dismissed outright?
- Does Esc close modals?
- Does a dedicated fast lane exist — shortcuts, bulk operations?

**Failures to name explicitly**:
- Tutorials that cannot be skipped
- Primary actions unreachable from the keyboard
- Sluggish animations with no way to cut through them
- Item-by-item flows in situations that clearly call for batch handling
- Confirmation prompts stacked onto actions that carry no real risk

---

## 2. Disoriented First-Timer — "Jordan"

**Who**: Has never touched a product in this category. Wants a hand at every turn. Gives up sooner than puzzle it out.

**Typical behavior**:
- Works through every instruction word by word
- Pauses before clicking anything unrecognized
- Keeps searching for help or support
- Trips over jargon and abbreviations
- Reads every label in its most literal sense

**Probe with**:
- Within five seconds, is the first move unmistakable?
- Does every icon carry a text label?
- Is help available right where decisions get made?
- Does the vocabulary presume knowledge Jordan lacks?
- Is there an obvious way back or undo at each step?

**Failures to name explicitly**:
- Unlabeled, icon-only navigation
- Technical vocabulary dropped in without explanation
- No help affordance anywhere in sight
- Murky next steps once an action completes
- Silence after an action succeeds — no confirmation at all

---

## 3. Assistive-Tech User — "Sam"

**Who**: Navigates by screen reader (VoiceOver or NVDA) and keyboard alone. May be living with low vision, a motor impairment, or cognitive differences.

**Typical behavior**:
- Moves through the page linearly via Tab
- Depends on ARIA labeling and a sane heading outline
- Never perceives hover states or anything signaled visually only
- Requires sufficient color contrast, with 4.5:1 as the floor
- May be running browser zoom as far as 200%

**Probe with**:
- Is the whole primary flow completable without a mouse?
- Is every interactive element focusable, with a focus indicator you can actually see?
- Does each image carry alt text that means something?
- Does contrast satisfy WCAG AA — 4.5:1 for text?
- Are state changes such as loading, success, and errors announced to the screen reader?

**Failures to name explicitly**:
- Interactions bound to click with no keyboard equivalent
- Focus indicators that are absent or invisible
- Information carried by color alone, such as red for error and green for success
- Form fields or buttons left unlabeled
- Timed actions that offer no way to request more time
- Bespoke components that derail screen reader navigation

---

## 4. Methodical Edge-Case Hunter — "Riley"

**Who**: A systematic user who deliberately leaves the happy path, feeds the interface unexpected input, and looks for holes in the experience.

**Typical behavior**:
- Goes after edge cases on purpose — empty states, enormous strings, special characters
- Feeds forms data they were never designed for: emoji, RTL text, absurdly long values
- Tries to derail flows by navigating backwards, refreshing halfway through, or opening several tabs
- Watches for gaps between what the UI claims and what it actually does
- Keeps an orderly record of every problem found

**Probe with**:
- How does it behave at the extremes — 0 items, 1000 items, enormous blocks of text?
- Do error states recover cleanly, or strand the UI in a broken condition?
- Refresh mid-flow: does state survive?
- Are there features that look functional but hand back broken output?
- What does unexpected input do — emoji, special characters, a paste straight out of Excel?

**Failures to name explicitly**:
- Features that seem fine yet fail quietly or return wrong results
- Error handling that leaks technical detail or leaves the UI wedged
- Empty states offering nothing actionable, such as a bare "No results"
- Flows that discard user data on refresh or navigation
- The same kind of interaction behaving differently in different corners of the product

---

## 5. Divided-Attention Mobile User — "Casey"

**Who**: On a phone, one hand, in motion. Interrupted constantly. Quite possibly on a poor connection.

**Typical behavior**:
- Operates by thumb, so favors controls near the bottom edge
- Gets pulled away mid-task and comes back later
- Hops between apps all day
- Runs on a short attention span and thin patience
- Avoids typing wherever tapping or picking will do

**Probe with**:
- Do the primary actions sit in the thumb zone, the lower half of the screen?
- If Casey leaves and returns, is state still there?
- Does it hold up over a slow 3G connection?
- Can forms lean on autocomplete and sensible defaults?
- Do touch targets measure at least 44×44pt?

**Failures to name explicitly**:
- Key actions parked at the top of the screen where a thumb cannot reach
- No persistence, so progress evaporates on a tab switch or interruption
- Long text entry demanded where a selection control would serve
- Every page dragging in heavy assets with no lazy loading
- Tap targets that are undersized or crowded together

---

## Choosing Which Personas to Run

Match the archetypes to what you are reviewing:

| Interface Type | Primary Personas | Why |
|---------------|-----------------|-----|
| Landing page / marketing | Jordan, Riley, Casey | Trust, first impression, phone-first traffic |
| Dashboard / admin | Alex, Sam | Throughput plus assistive-tech support |
| E-commerce / checkout | Casey, Riley, Jordan | Phone use, edge cases, plain-language clarity |
| Onboarding flow | Jordan, Casey | Getting lost, getting interrupted |
| Data-heavy / analytics | Alex, Sam | Speed of work and keyboard reach |
| Form-heavy / wizard | Jordan, Sam, Casey | Comprehension, assistive tech, small screens |

---

## Personas Derived From the Project

When `.uicraft.md` carries a `## Design Context` section produced by `uicraft-init`, mine the audience and brand notes for one or two extra archetypes:

1. Read through the described target audience
2. Work out which primary archetype the five above fail to represent
3. Write the new persona against this shape:

```
### [Role] — "[Name]"

**Who**: [2-3 defining traits pulled straight from Design Context]

**Typical behavior**: [3-4 concrete habits implied by the described audience]

**Failures to name explicitly**: [3-4 things guaranteed to lose this particular user]
```

Do this only when genuine Design Context data exists. Never fabricate audience details — with no context on hand, the five standard archetypes are the whole set.
