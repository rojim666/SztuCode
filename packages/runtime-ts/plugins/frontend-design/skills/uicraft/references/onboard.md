---
name: onboard
description: Shapes first-run experiences, activation paths, and empty states so newcomers reach value fast. Use when the user mentions onboarding, first-time users, empty states, activation, getting started, or new user flows.
---

## Contents

- [MANDATORY PREPARATION](#mandatory-preparation)
- [Frame the Problem](#frame-the-problem)
- [Guiding Principles](#guiding-principles)
- [Build the Experience](#build-the-experience)
- [Anatomy of an Empty State](#anatomy-of-an-empty-state)
- [Shipping It](#shipping-it)
- [Measure Whether It Worked](#measure-whether-it-worked)


## MANDATORY PREPARATION

Start from the priorities in the main SKILL.md. Take Design Context from the current instructions, or from `.uicraft.md` if the project has one. If important product or brand context is still missing, consult [uicraft-init.md](uicraft-init.md) and ask a few targeted questions; otherwise state conservative assumptions and continue. Two extra inputs matter here: the "aha moment" users should reach, and their experience level.

---

Design or repair the path that carries a newcomer from first launch to real competence, as fast as that can honestly be done.

## Frame the Problem

Work out what has to be learned, and why:

1. **Name the obstacle**:
   - What is the user trying to get done?
   - Which parts of today's experience read as murky?
   - Where do people stall out or drop off?
   - Which moment is the "aha moment" you are steering toward?

2. **Profile the audience**:
   - How skilled — novices, veterans, or mixed?
   - What brought them here — curiosity, or a mandate from work?
   - How much time will they give you — five minutes, or thirty?
   - What are they comparing you against — a competitor they just left, or nothing, because the category is new to them?

3. **Decide what winning looks like**:
   - What is the least someone must learn to succeed?
   - Which single action matters most — a first project, a first invite?
   - Which signal proves it worked — completion rate, time to value?

**CRITICAL**: Onboarding exists to deliver value fast, not to cover the product's full surface area.

## Guiding Principles

Five ideas govern every decision below.

### Demonstrate Instead of Describing
- Let a working example carry the explanation
- Keep users in the real product; don't fork them into a fake tutorial mode
- Disclose progressively — one idea per beat

### Keep It Escapable
- Let anyone who already knows the product walk past it
- Never gate product access behind it
- Offer an explicit out: "Skip", or "I'll explore on my own"

### Shorten Time to Value
- Drive to the "aha moment" with minimal detour
- Front-load the concepts that matter most
- Cover the 20% of the product responsible for 80% of the payoff
- Leave advanced capability for contextual discovery later

### Prefer Context to Ceremony
- Introduce a feature when it becomes relevant, not in an upfront lecture
- Treat every empty state as a teaching surface
- Place hints and tooltips where the action happens

### Assume Competence
- Don't talk down or belabor the obvious
- Keep the writing short and unambiguous
- Trust users to recognize conventional patterns unnarrated

## Build the Experience

Match the format to the situation.

### The First Run

**Welcome screen**:
- One clear line of value proposition — what is this product?
- What the user will be able to do afterwards
- An honest estimate of the time it takes
- A skip route for people who already know their way around

**Account setup**:
- Ask the bare minimum; collect the rest later
- Justify every field you do ask for
- Prefill sensible defaults
- Offer social login where it fits

**Core concepts**:
- One to three ideas, not the whole model
- Plain words, concrete examples
- Hands-on rather than read-only where possible
- Position in the sequence ("step 1 of 3")

**First win**:
- Have the user complete something genuine
- Seed templates or sample content so the action succeeds
- Mark the achievement, but don't throw a parade
- Point clearly at what comes next

### Discovery After the First Run

**Empty states** — a blank region is wasted space. Put in it:
- What will eventually live there, described and illustrated
- Why that is worth having
- A direct call to action for creating the first item
- A template or example as an alternate starting point

Example:
```
No dashboards yet
Dashboards pull your team's key metrics onto one screen.
[Create your first dashboard] or [Start from template]
```

**Contextual tooltips**:
- Fire the first time someone meets the feature
- Anchor visually to the element in question
- One line of explanation, paired with the benefit
- Dismissible, including a "Don't show again" option
- An optional "Learn more" link

**Feature announcements**:
- Surface new capability as it ships
- Say what changed and why it's worth caring about
- Make it try-able on the spot
- Dismissible

**Progressive onboarding**:
- Teach each feature at the point of encounter
- Flag new or untouched features with badges or indicators
- Reveal complexity in stages instead of exposing every option at once

### Guided Tours and Walkthroughs

**Reach for one when**:
- The interface is large and genuinely feature-dense
- An existing product has changed substantially
- The tool is industry-specific and assumes domain knowledge

**Designing it**:
- Spotlight the element under discussion; dim the rest of the page
- Cap it at three to seven steps
- Let people advance at their own pace
- Always include "Skip tour"
- Make it replayable from the help menu

**What makes tours work**:
- Interaction beats observation — let users press real buttons
- Organize around a workflow, not a component inventory ("Create a project", not "This is the project button")
- Supply sample data so the steps genuinely function

### Interactive Tutorials

**Reach for one when**:
- The material requires practice
- The concepts are complex or unfamiliar
- Stakes are high enough that rehearsing somewhere safe is preferable

**Designing it**:
- A sandbox stocked with sample data
- An explicit goal ("Create a chart showing sales by region")
- Step-by-step guidance
- Validation that they got it right
- A graduation beat that says they're ready

### Help and Documentation

**Inside the product**:
- Contextual help links threaded through the interface
- A keyboard shortcut reference
- A searchable help center
- Video for the workflows that resist text

**Conventional touchpoints**:
- A `?` icon beside anything complex
- "Learn more" links inside tooltips
- Inline shortcut hints, such as `⌘K` printed in the search box

## Anatomy of an Empty State

Five ingredients belong in every empty state:

### The Content That Will Live Here
"Your recent projects will appear here"

### The Reason to Care
"Projects help you organize your work and collaborate with your team"

### The Way In
[Create project] or [Import from template]

### Something to Look At
An illustration or icon — never bare text stranded on a white page

### A Path to Help
"Need help getting started? [Watch 2-min tutorial]"

The copy should also reflect which kind of emptiness you're in:

- **Never used** — the feature is untouched; lead with value, offer a template
- **Deliberately emptied** — cleared on purpose; light touch, easy to recreate
- **Nothing matched** — a search or filter came back empty; propose another query or clear the filters
- **Access denied** — explain the block and how to request access
- **Load failed** — say what broke and offer a retry

## Shipping It

### Libraries and mechanics

**Tooltip libraries**: Tippy.js, Popper.js
**Tour libraries**: Intro.js, Shepherd.js, React Joyride
**Modal patterns**: Focus trap, backdrop, ESC to close
**Progress tracking**: LocalStorage for "seen" states
**Analytics**: Track completion, drop-off points

**Persisting what's been seen**:
```javascript
// Remember which onboarding moments this user has already passed
localStorage.setItem('onboarding:v1:done', 'true');
localStorage.setItem('tooltip-seen:billing-panel', 'true');
```

**IMPORTANT**: Running the same onboarding at someone twice is irritating. Persist completion state and honor every dismissal.

Things that reliably ruin onboarding, and should therefore be avoided:

- Forcing a long sequence before the product becomes usable
- Explaining the obvious in a tone that talks down to the reader
- Re-firing a tooltip the user already dismissed
- Freezing the whole UI during a tour instead of letting people wander
- Standing up a tutorial mode disconnected from the real product
- Dumping everything up front — progressive disclosure exists to prevent exactly this
- Burying "Skip" or making it hard to find
- Neglecting returning users by replaying the first-run flow at them

## Measure Whether It Worked

Put it in front of real users and watch these signals:

- **Time to completion** — how long does getting through take?
- **Comprehension** — do people understand once they're done?
- **Action** — do they take the next step you wanted?
- **Skip rate** — a high one means it runs too long or reads as low value
- **Completion rate** — if it's low, cut the flow down
- **Time to value** — how long until the first real payoff?

Approach the work as a teacher would: reach the "aha moment" quickly, teach only the essential, deliver it in context, and respect both the user's time and their intelligence.
