---
name: Heuristics Scoring
description: A 0-4 rubric built on Nielsen's ten usability heuristics, used to audit an interface systematically and write up the findings.
---

## Contents

- [The Ten Heuristics](#the-ten-heuristics)
- [Reading the Total](#reading-the-total)
- [Ranking Individual Issues (P0–P3)](#ranking-individual-issues-p0p3)


# Heuristics Scoring Guide

Rate the interface against each of Nielsen's ten usability heuristics from 0 to 4. Grade strictly: reserve 4 for work that is genuinely exemplary, not merely acceptable.

## The Ten Heuristics

### 1 — Visibility of System Status

The product should always tell the user what it is doing, promptly and in the right place.

**Look for**:
- Spinners, skeletons, or other signals while asynchronous work runs
- Acknowledgement after a save, a submit, or a delete
- Step counters or progress bars in multi-stage flows
- A visible sense of where you are — breadcrumbs, active nav states
- Validation that surfaces inline rather than only at submit time

**Score it**:
| Score | What it looks like |
|:-----:|----|
| 0 | Silence — the user has to guess whether anything happened |
| 1 | Almost nothing responds visibly to most actions |
| 2 | Some states are reported; sizeable blind spots remain |
| 3 | Feedback is clear for nearly all operations, with small gaps |
| 4 | Every action is acknowledged and progress is never hidden |

### 2 — Match Between System and Real World

Use the vocabulary of the people using the product, honor conventions they already know, and order information the way they expect to encounter it.

**Look for**:
- Terminology the audience recognizes, with no unexplained jargon
- Sequencing that matches how users think about the task
- Icons and metaphors that read correctly on first glance
- Register and vocabulary suited to the specific domain and audience
- Layout that respects natural reading order — left to right, top priority first

**Score it**:
| Score | What it looks like |
|:-----:|----|
| 0 | Engineering vocabulary throughout; foreign to the actual user |
| 1 | Largely opaque — you need domain expertise just to navigate |
| 2 | Uneven; plain language in places, jargon leaking in elsewhere |
| 3 | Reads naturally, with the occasional term that needs a gloss |
| 4 | Fluent in the user's own language from end to end |

### 3 — User Control and Freedom

Anyone who lands somewhere they did not intend needs an obvious way back out, without negotiating for it.

**Look for**:
- Undo and redo
- Cancel affordances on forms and modals
- An unambiguous path back to safety — home, or the previous screen
- One-step clearing of filters, searches, and selections
- A way to abandon a long or multi-step process partway through

**Score it**:
| Score | What it looks like |
|:-----:|----|
| 0 | Dead ends — reloading the page is the only escape |
| 1 | Exits exist but are obscure and hard to reach |
| 2 | The main flows offer a way out; edge cases trap the user |
| 3 | Most actions can be exited or reversed |
| 4 | Undo, cancel, back, and escape are available everywhere |

### 4 — Consistency and Standards

Nobody should have to work out whether two different words, screens, or gestures actually mean the same thing.

**Look for**:
- One vocabulary applied across the whole interface
- Identical actions producing identical outcomes wherever they appear
- Adherence to platform conventions and standard UI patterns
- Visual coherence in color, type, spacing, and components
- Interaction parity — the same gesture always does the same thing

**Score it**:
| Score | What it looks like |
|:-----:|----|
| 0 | Reads like several products bolted together |
| 1 | Frequent divergence — comparable things look and act differently |
| 2 | Core flows line up while the details drift apart |
| 3 | Broadly consistent; the rare deviation causes no confusion |
| 4 | One cohesive system with entirely predictable behavior |

### 5 — Error Prevention

A design that makes the mistake impossible beats even the best-written error message.

**Look for**:
- A confirmation step ahead of destructive operations such as delete or overwrite
- Input constrained by the control itself — date pickers, dropdowns
- Defaults chosen to steer users away from mistakes
- Labels precise enough that misreading them is unlikely
- Autosave and recoverable drafts

**Score it**:
| Score | What it looks like |
|:-----:|----|
| 0 | Nothing guards anything; mistakes are trivially easy |
| 1 | Sparse safeguards — a few inputs validated, most unchecked |
| 2 | Common mistakes are caught while edge cases get through |
| 3 | Most error paths are closed off before the user reaches them |
| 4 | Constraints are designed well enough that errors are near-impossible |

### 6 — Recognition Rather Than Recall

Keep the memory burden low: what users need should be on screen or a keystroke away, not stored in their heads.

**Look for**:
- Options exposed rather than buried in hidden menus
- Help delivered in context — tooltips, inline hints
- History and recently used items
- Suggestions and autocomplete offered as the user types
- Icons carrying labels instead of icon-only navigation

**Score it**:
| Score | What it looks like |
|:-----:|----|
| 0 | Users must memorize paths and commands to get anywhere |
| 1 | Recall-driven — many features hidden, few visible cues |
| 2 | Primary actions are visible; secondary features stay concealed |
| 3 | Most things are discoverable and little memorization is required |
| 4 | Everything is findable; nothing has to be remembered |

### 7 — Flexibility and Efficiency of Use

Shortcuts that beginners never notice should let experienced users move fast.

**Look for**:
- Keyboard shortcuts covering frequent actions
- Interface elements the user can configure
- Favorites and recently opened items
- Operations that apply to many items at once
- Advanced capabilities that stay out of the way of basic use

**Score it**:
| Score | What it looks like |
|:-----:|----|
| 0 | A single rigid route with no shortcuts or alternatives |
| 1 | Barely any alternative to the one main path |
| 2 | Rudimentary keyboard support and limited batch operations |
| 3 | Solid accelerators — keyboard navigation plus some customization |
| 4 | Many routes through the product, power features, user-configurable |

### 8 — Aesthetic and Minimalist Design

Anything irrelevant or seldom needed dilutes what matters; each element on screen must justify its presence.

**Look for**:
- Only the information the current step requires
- A hierarchy that steers the eye deliberately
- Color and emphasis spent on purpose rather than for decoration
- No ornamental noise competing with content
- Layouts that stay focused and uncrowded

**Score it**:
| Score | What it looks like |
|:-----:|----|
| 0 | Everything shouts at once; nothing is prioritized |
| 1 | Noisy enough that finding what matters is work |
| 2 | The main content is legible but the periphery is busy |
| 3 | Largely clean with a little residual visual noise |
| 4 | Nothing extraneous survives — every element earns its pixel |

### 9 — Help Users Recognize, Diagnose, and Recover from Errors

When something fails, say it in plain words, pinpoint exactly what went wrong, and offer a way forward.

**Look for**:
- Messages written in plain language, with no raw error codes shown to users
- Precise diagnosis — "Email is missing @" rather than "Invalid input"
- A suggested next step the user can actually take
- The message placed next to whatever caused it
- Failure handled without destroying work already entered in the form

**Score it**:
| Score | What it looks like |
|:-----:|----|
| 0 | Codes, jargon, or no message at all |
| 1 | "Something went wrong" and nothing else to go on |
| 2 | The problem is named but no remedy is offered |
| 3 | Both the problem and a next step are communicated |
| 4 | Exact cause, a concrete fix, and the user's input left intact |

### 10 — Help and Documentation

A product may be usable without docs and still need them findable, task-shaped, and short.

**Look for**:
- Documentation or help that can be searched
- Assistance delivered in place — tooltips, inline hints, guided tours
- Content organized around tasks rather than around the feature list
- Writing that is brief and easy to scan
- Access that does not force the user out of what they were doing

**Score it**:
| Score | What it looks like |
|:-----:|----|
| 0 | There is no help of any kind |
| 1 | Help exists but is buried or beside the point |
| 2 | An FAQ or docs site exists, but nothing is contextual |
| 3 | Searchable documentation organized mostly by task |
| 4 | The right guidance appears exactly when it is needed |

---

## Reading the Total

Ten heuristics at a maximum of 4 each gives a ceiling of **40 points**.

| Range | Verdict | Interpretation |
|:-----:|--------|----|
| 36–40 | Excellent | Nothing but polish left; ship it |
| 28–35 | Good | The base is sound — go after the weak dimensions |
| 20–27 | Acceptable | Real work is required before users will be satisfied |
| 12–19 | Poor | The core experience is broken; a UX overhaul is warranted |
| 0–11 | Critical | Unusable as it stands and needs redesigning |

---

## Ranking Individual Issues (P0–P3)

Every specific problem you record while scoring gets its own priority tag:

| Priority | Label | When it applies | Response |
|:--------:|------|----|----|
| **P0** | Blocking | The user cannot finish the task at all | Showstopper — fix it now |
| **P1** | Major | Causes real confusion or difficulty | Must be resolved before release |
| **P2** | Minor | Irritating, but a workaround exists | Schedule for the next pass |
| **P3** | Polish | No meaningful impact on users | Fix if the schedule allows |

**Tiebreaker**: when a finding sits between two levels, ask whether a user would open a support ticket over it. If the answer is yes, rate it P1 or higher.
