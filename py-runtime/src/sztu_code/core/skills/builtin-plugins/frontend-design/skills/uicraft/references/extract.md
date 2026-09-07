---
name: extract
description: Pull recurring UI patterns, shared components, and design tokens out of feature code and fold them into the design system. Use when the user wants to build a component library, systematize repeated markup, define tokens, or refactor duplicated interface code into shared primitives.
---

Find what repeats, decide what deserves to be shared, then lift it into the design system so future work inherits it for free.

Load `.uicraft.md` from the project root first if it exists. Naming and abstraction choices should echo the aesthetic direction recorded there rather than inventing a parallel vocabulary.

## Survey what already exists

Never extract into a vacuum. Locate the destination before you touch the source.

Search the repository for a design system, component library, or shared UI directory — grep for terms like "design system", "ui", "components". Once found, read it for:

- how components are grouped and named
- whether design tokens exist, and how they are layered
- the documentation style already in use
- import and export conventions

**If no design system exists, stop and ask.** Creating one is a structural decision: the location, the layering, and the conventions all need the user's input before any file gets written.

## Spot the candidates

Four kinds of duplication are worth hunting for:

- **Components that repeat** — buttons, cards, inputs, and similar elements rebuilt in several places
- **Literals that should be tokens** — colors, spacing values, type sizes, and shadows hard-coded inline
- **Divergent takes on one idea** — three button styles that were all meant to be the same button
- **Structural habits** — layout skeletons, composition shapes, and interaction sequences that recur

## Filter by value, not by frequency alone

Extraction has a cost. Weigh each candidate:

- Has it appeared three or more times, or is reuse clearly coming?
- Does centralizing it actually buy consistency, or just indirection?
- Is the pattern genuinely general, or is it fused to one screen's context?
- Will the shared version be cheaper to maintain than the copies?

Candidates that fail these questions stay where they are.

## Draft the extraction plan

Write the plan down before editing anything:

- which elements graduate into components
- which literals become tokens
- what variants each component must cover
- names for components, tokens, and props that sit naturally beside what exists
- the route for migrating current call sites onto the shared version

Keep the plan tight. Design systems accrete — take what is demonstrably reusable today and leave speculative abstractions for the day they earn their place.

## Build the shared version properly

Extraction is a chance to improve the thing, not just relocate it.

For **components**, ship:

- a props API that is small, predictable, and usefully defaulted
- variants that cover the real use cases you found
- accessibility wired in from the start — ARIA, keyboard operation, focus handling
- usage documentation with worked examples

For **tokens**, ship:

- names that distinguish primitive values from semantic roles
- a coherent hierarchy rather than a flat dump
- notes on which token to reach for in which situation

For **patterns**, ship:

- the conditions that make the pattern the right choice
- example code
- the variations and combinations it supports

Watch for these failure modes. Lifting a one-off implementation without generalizing it just moves the problem. Abstracting so hard that the component can no longer express anything produces a shell nobody uses. Ignoring the conventions of the design system you are adding to creates a second, competing system. Shipping without TypeScript types or prop documentation pushes the cost onto every future caller. And minting a token for every literal drains tokens of meaning — a token should stand for a decision, not merely for a value.

## Cut the old code over

A shared version that nothing consumes is dead weight:

- locate every instance of the pattern you extracted
- rewrite each call site onto the shared version
- confirm parity, both visual and behavioral
- delete the implementations you replaced

## Record it

Close the loop in the documentation:

- register new components in the library
- publish token values alongside guidance on their use
- supply examples and usage guidelines
- refresh Storybook or whatever component catalog the project keeps

A design system is worth having only while it stays alive. Harvest patterns as they surface, sharpen them on the way in, and keep them tended.
