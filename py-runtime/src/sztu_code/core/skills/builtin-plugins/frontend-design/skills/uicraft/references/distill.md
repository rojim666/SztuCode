---
name: distill
description: Reduce a design to what actually matters by cutting away the complexity around it. Strong work is spare, clear, and purposeful. Use when the user asks to simplify, declutter, quiet things down, strip elements out, or sharpen the focus of an interface.
---

## Contents

- [Before You Start](#before-you-start)
- [Read The Clutter](#read-the-clutter)
- [Decide What Survives](#decide-what-survives)
- [Cut Across Every Layer](#cut-across-every-layer)
- [Confirm It Actually Helped](#confirm-it-actually-helped)
- [Record What You Removed](#record-what-you-removed)


Strip out the complexity a design does not need, so the elements that carry the work become visible and the whole thing reads clearly.

## Before You Start

Begin from the priorities set out in the main SKILL.md. Pull Design Context from the current instructions or from `.uicraft.md` whenever either supplies it. If product or brand context that would materially change your decisions is still missing, consult [uicraft-init.md](uicraft-init.md) and ask a small number of targeted questions; when that is not practical, write down conservative assumptions and carry on.

---

## Read The Clutter

Work out precisely where the sense of clutter comes from.

**Sources of complexity to name**:
- **Element overload** — buttons competing with each other, information stated twice, visual debris
- **Unpurposeful variety** — a spread of colors, typefaces, sizes, and styles that no rationale supports
- **Everything at once** — the whole payload on screen, nothing deferred through progressive disclosure
- **Decorative noise** — borders, shadows, backgrounds, and ornament that earn nothing
- **Muddy hierarchy** — no clear signal about what deserves attention first
- **Feature creep** — an excess of options, actions, and possible next moves

**Then locate the essence**:
- What is the user here to do? There should be exactly one answer.
- Which parts are required, and which are merely pleasant to have?
- What could be deleted, deferred behind a control, or merged with something else?
- Which 20% of this produces 80% of the value?

Where the code cannot tell you the answer, put the question to the user rather than guessing.

**CRITICAL**: simplifying is not the same as removing capability. What you are removing is whatever stands between a person and the outcome they came for. Every element on screen has to earn its place.

## Decide What Survives

Set an editing strategy before you touch anything:

- **Core purpose** — the single job this surface exists to do
- **Essential elements** — what that job genuinely requires
- **Progressive disclosure** — what can wait out of sight until it is relevant
- **Consolidation opportunities** — what can be folded together or absorbed elsewhere

**IMPORTANT**: this is difficult work. Turning down good ideas is what leaves room for one idea to be executed well. Hold the line.

## Cut Across Every Layer

Work through each dimension in turn.

### Information Architecture
- **Narrow the scope**: drop secondary actions, optional features, and anything already stated elsewhere
- **Defer the rest**: put complexity behind an obvious entry point — an accordion, a modal, a stepped flow
- **Fold actions together**: merge near-duplicate buttons, collapse forms into one, group related content
- **Make the hierarchy legible**: one primary action, a small number of secondary ones, everything remaining tertiary or hidden
- **Say it once**: if the point is made elsewhere, it does not need repeating here

### Visual Treatment
- **Shrink the palette**: one or two colors alongside neutrals, rather than five to seven
- **Constrain type**: a single family, no more than 3-4 sizes, 2-3 weights
- **Delete ornament**: borders, shadows, and backgrounds that serve neither hierarchy nor function come out
- **Flatten the structure**: less nesting, fewer wrapper elements, and never a card inside another card
- **Question every card**: plain layout does not need one; spacing and alignment do the job
- **Standardize spacing**: a single scale, with arbitrary one-off gaps removed

### Layout
- **Go linear**: where a complex grid can become a simple vertical flow, let it
- **Lose the sidebar**: bring secondary content inline or hide it altogether
- **Use the width**: spend the available space rather than inventing multi-column complexity
- **Commit to one alignment**: left or center, then stay with it
- **Leave room**: content needs air; resist packing it in

### Interaction
- **Offer fewer choices**: fewer buttons and fewer options make the path forward clearer — the paradox of choice is not a myth
- **Default intelligently**: decide the common case automatically and only ask when you must
- **Edit in place**: prefer inline editing to a modal flow wherever it fits
- **Delete steps**: could signup collapse from three screens to one? Could checkout lose a stage?
- **One clear CTA**: a single obvious next step, never five actions competing

### Copy
- **Cut length**: halve every sentence, then halve it again
- **Write active**: "Save changes", not "Changes will be saved"
- **Drop the jargon**: plain words win every time
- **Make it scannable**: short paragraphs, bullets, headings that mean something
- **Keep only what informs**: marketing filler, legalese, and hedging go
- **Stop repeating yourself**: no heading that restates the intro, no explanation given twice

### Code
- **Delete what nothing uses**: dead CSS, abandoned components, orphaned files
- **Flatten component trees**: bring the nesting depth down
- **Consolidate styles**: merge near-identical rules and apply utilities consistently
- **Trim variants**: does that component really need 12, or would 3 cover 90% of usage?

Six lines you should not cross while cutting. Do not strip out functionality that is genuinely needed — simple is not the same as featureless. Do not trade accessibility for tidiness; labels and ARIA remain non-negotiable. Do not simplify past the point of clarity, because mystery is not minimalism. Do not remove the information people rely on to make a decision. Do not level the hierarchy entirely — some things are supposed to dominate. And do not force a genuinely complex domain to look simple; the interface should match the difficulty of the real task.

## Confirm It Actually Helped

Simplification has to pay off in use:

- **Speed**: do people reach their goal faster now?
- **Effort**: is it easier to tell what to do?
- **Completeness**: is every necessary capability still reachable?
- **Hierarchy**: is the most important thing unmistakable?
- **Performance**: does the leaner version load faster?

## Record What You Removed

When features or options came out, leave a trail:
- the reasoning behind each removal
- whether any of them need another way in
- which user reactions are worth watching

Trust your judgment: knowing what to protect, and having the nerve to delete the rest, is what makes this an act of confidence rather than loss. Saint-Exupéry put the standard well — "Perfection is achieved not when there is nothing more to add, but when there is nothing left to take away."
