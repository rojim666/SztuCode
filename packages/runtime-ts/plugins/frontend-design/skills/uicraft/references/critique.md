---
name: critique
description: Judge an interface as a designed experience — visual hierarchy, information architecture, emotional resonance, cognitive load — and return a scored, persona-tested, actionable verdict. Use when the user asks you to review, critique, evaluate, or give feedback on a design or component.
---

## Contents

- [MANDATORY PREPARATION](#mandatory-preparation)
- [Phase 1: Run the Critique](#phase-1-run-the-critique)
- [Phase 2: Report the Findings](#phase-2-report-the-findings)
- [Phase 3: Put Questions Back to the User](#phase-3-put-questions-back-to-the-user)
- [Phase 4: Propose the Action Plan](#phase-4-propose-the-action-plan)


## MANDATORY PREPARATION

Before proceeding, apply the main SKILL.md priorities. Use Design Context from the current instructions or `.uicraft.md` when available. If high-impact product or brand context is still missing, read [uicraft-init.md](uicraft-init.md) and ask only focused questions; otherwise state conservative assumptions and continue. Additionally gather: what the interface is trying to accomplish.

---

Assess the interface whole, not piece by piece: does it succeed as a designed experience, and not merely as working code? Deliver the verdict the way a design director would deliver it.

## Phase 1: Run the Critique

Work through each of the following lenses.

### 1. Generic-AI Detection (CRITICAL)

**Nothing else in this list matters more.** Could this be swapped with any other AI-generated interface from 2024-2025 without anyone noticing?

Hold the design up against every **DON'T** in this skill — those items are the fingerprints AI-generated work leaves behind. Hunt specifically for the AI color palette, gradient text, dark mode lit by glowing accents, glassmorphism, hero metric layouts, cloned card grids, default fonts, and the rest of the tells.

**The test**: Announce "AI made this" to a stranger looking at the screen. If they accept it on the spot, you have found the problem.

### 2. Where the Eye Lands

- Does the eye land on the most important element first?
- Is one primary action clearly dominant, and can you find it inside two seconds?
- Are size, color, and placement encoding importance correctly?
- Are elements of deliberately different weight fighting each other for attention?

### 3. Structure & Mental Effort
> *Consult [cognitive-load](cognitive-load.md) for the working memory rule and 8-item checklist*

- Does the organization make immediate sense to somebody arriving cold?
- Is related material actually sitting together?
- How many options are visible at each decision point? Count them — anything above 4 gets flagged
- Is the navigation both legible and predictable?
- **Progressive disclosure**: does complexity arrive when it is needed, or land on the user all at once up front?
- **Work the 8-item cognitive load checklist** from the reference and report how many items fail: 0–1 is low (good), 2–3 is moderate, 4 or more is critical.

### 4. The Emotional Arc

- Which feeling does this produce — and was that feeling chosen on purpose?
- Is it aligned with the brand's personality?
- Whatever it is supposed to project — trustworthy, approachable, premium, playful — does it land?
- Would somebody in the target audience recognize it as built for them?
- **Peak-end rule**: is the highest-intensity moment a positive one, and does the experience close well with a confirmation, a celebration, or an obvious next step?
- **Emotional valleys**: look for friction during onboarding, error cliffs, features nobody can find, and anxiety spikes around high-stakes actions such as payment, deletion, or commit
- **Interventions at negative moments**: where frustration or anxiety is likely, is anything designed to absorb it — progress indicators, reassuring copy, an undo path, social proof?

### 5. Affordance & Findability

- Do interactive elements read as interactive?
- Could someone operate this without being told how?
- Are hover and focus states returning useful information?
- Is anything valuable buried that deserves to be visible?

### 6. Balance of the Composition

- Does the arrangement sit comfortably, or does it feel lopsided?
- Is the whitespace a decision, or just the space nothing else filled?
- Do spacing and repetition produce a rhythm?
- When the layout goes asymmetric, does that read as intent or as accident?

### 7. Type as a Signal

- Does the type hierarchy make the reading order unmistakable — first, second, third?
- Is running text comfortable to read across line length, leading, and size?
- Do the typefaces support the brand and its tone?
- Is there enough separation between heading levels?

### 8. Color Doing Work

- Is color carrying meaning, or only decorating?
- Does the palette hang together?
- Are accents pointing at the things that deserve attention?
- Does it survive colorblind vision — not just passing a checker, but still communicating what it means?

### 9. The Non-Happy Paths

- Empty states: do they push the user toward an action, or merely announce that nothing is there?
- Loading states: do they shrink the perceived wait?
- Error states: are they useful, and do they avoid blaming the user?
- Success states: do they confirm what happened and point at what comes next?

### 10. Voice & Microcopy

- Is the writing clear and economical?
- Does it sound like a person — and specifically the kind of person this brand would be?
- Are labels and buttons free of ambiguity?
- Does error copy actually help the user recover?

## Phase 2: Report the Findings

Present the results in the order a design director would.

### Heuristic Scorecard
> *Consult [heuristics-scoring](heuristics-scoring.md)*

Rate all ten of Nielsen's heuristics on a 0–4 scale and lay them out in a table:

| # | Heuristic | Score | Finding |
|---|-----------|-------|---------|
| 1 | Visibility of System Status | _ | [name the specific problem, or "—" when it holds up] |
| 2 | Match System / Real World | _ | |
| 3 | User Control and Freedom | _ | |
| 4 | Consistency and Standards | _ | |
| 5 | Error Prevention | _ | |
| 6 | Recognition Rather Than Recall | _ | |
| 7 | Flexibility and Efficiency | _ | |
| 8 | Aesthetic and Minimalist Design | _ | |
| 9 | Error Recovery | _ | |
| 10 | Help and Documentation | _ | |
| **Total** | | **__/40** | **[Rating band]** |

Score honestly. Reserve 4 for work that is genuinely excellent; interfaces in the wild typically land somewhere in the 20–32 range.

### The Generic-AI Verdict
**Open with this.** Give a straight pass or fail on whether the work looks AI-generated, and cite the exact tells from the skill's Anti-Patterns section. Do not soften it.

### First Reaction
Your immediate reaction in a few sentences — what lands, what does not, and the one opportunity worth the most.

### Genuine Strengths
Call out two or three genuine strengths, and explain precisely why each one succeeds.

### Ranked Problems
List the three to five highest-impact problems in rank order.

Attach a **P0–P3 severity** tag to each one — severity definitions live in [heuristics-scoring](heuristics-scoring.md):

- **[P?] What**: state the problem plainly
- **Why it matters**: the damage it does to users or to the product's goals
- **Fix**: the concrete change to make
- **Suggested next workflow**: Name the relevant UICraft workflow and the specific issue it should address

### Red Flags by Persona
> *Consult [personas](personas.md)*

Pick the two or three personas that fit this kind of interface, using the selection table in [personas.md](personas.md). When `.uicraft.md` carries a `## Design Context` section written by `uicraft-init`, derive one or two additional project-specific personas from the audience and brand details there.

Take each chosen persona through the interface's primary action and record exactly what trips them up:

**Alex (Power User)**: Zero keyboard shortcuts anywhere. Primary action buried behind 8 clicks. Onboarding modal cannot be dismissed. ⚠️ High abandonment risk.

**Jordan (First-Timer)**: Sidebar navigation is icons only. Errors speak in jargon ("404 Not Found"). Help is nowhere on screen. ⚠️ Will abandon at step 2.

Point at the actual elements and interactions that failed. Skip the generic persona biography and report the breakage.

### Smaller Notes
Short notes covering the smaller issues still worth fixing.

**Hold yourself to this**:

- Say it plainly — hedged feedback costs everyone time
- Name the thing — "the submit button", never "some elements"
- Pair every defect with the reason it hurts users
- Propose an actual change rather than inviting the reader to "consider exploring..."
- Rank without mercy; a list where everything is critical ranks nothing
- Resist the urge to cushion the blow — shipping great design depends on honest feedback

## Phase 3: Put Questions Back to the User

**Once the findings are on the table**, ask about what you genuinely cannot infer, anchoring every question in what you actually found. The answers determine the plan.

Questions in this vein work well — always tailored to the real findings, never generic:

1. **Priority direction**: given the issues you surfaced, find out which category the user cares about most right now. Something like: "I found problems with visual hierarchy, color usage, and information overload. Which area should we tackle first?" Present the top two or three categories as choices.

2. **Design intent**: when the critique flags a tonal mismatch, check whether it was deliberate. Something like: "The interface feels clinical and corporate. Is that the intended tone, or should it feel warmer/bolder/more playful?" Offer two or three tonal directions drawn from what would actually resolve the issues.

3. **Scope**: establish how much work the user wants to sign up for. Something like: "I found N issues. Want to address everything, or focus on the top 3?" Give concrete options such as "Top 3 only", "All issues", or "Critical issues only".

4. **Constraints** (optional — raise it only when it applies): if the findings sprawl across many areas, ask whether anything is off the table. Something like: "Should any sections stay as-is?" This keeps the plan away from work the user already considers finished.

**Constraints on the questions**:

- Anchor every question to a specific Phase 2 finding; never fall back to generic prompts like "who is your audience?"
- Cap it at two to four questions out of respect for the user's time
- Hand over concrete options instead of open-ended prompts
- When the findings are simple — say one or two unmistakable issues — skip the questions entirely and move straight to Phase 4

## Phase 4: Propose the Action Plan

**Once the user has answered**, lay out a prioritized summary that honors the priorities and the scope they chose in Phase 3.

### The Recommended Sequence

Order the recommended next workflows by priority, guided by the user's answers:

1. **Workflow name** — Brief description of what to fix, tied to a specific finding
2. **Workflow name** — Brief description tied to a specific finding
3. ...and so on down the list

**Constraints on the recommendations**:

- Draw only from the workflows the main SKILL.md lists
- Sort by the priorities the user stated, then by impact
- Write each description with enough context that the command knows exactly where to aim
- Every ranked problem should map onto some workflow
- Drop any workflow that would resolve nothing
- Honor a narrowed scope by listing only what falls inside it
- Honor off-limits areas by excluding any command that would reach into them
- Close with the polish workflow whenever fixes were recommended

Follow the summary with this note to the user:

> Tell me to work through these one at a time, or to implement the prioritized set in one pass.
> Once the fixes land, run the UICraft critique again to confirm the result.
