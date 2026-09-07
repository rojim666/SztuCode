---
name: portfolio
description: Design and build personal portfolio, resume, and "about me" sites for individuals — designers, engineers, writers, researchers, and other practitioners showcasing their own work. Use when the user asks for a personal portfolio, personal site, resume site, or "about me" page.
---

## Contents

- [MANDATORY PREPARATION](#mandatory-preparation)
- [What Makes a Portfolio Different](#what-makes-a-portfolio-different)
- [Structural Anatomy](#structural-anatomy)
- [Choose a Style Direction](#choose-a-style-direction)
- [Portfolio Anti-Patterns](#portfolio-anti-patterns)
- [Content & UX Considerations](#content-ux-considerations)
- [Verify](#verify)

A personal portfolio sells a person, not a product. The design itself is evidence of taste and craft — for some audiences (designers, front-end engineers) the site *is* a work sample; for others (researchers, backend engineers, writers) the design should recede so the work and words carry the case.

## MANDATORY PREPARATION

Before proceeding, apply the main SKILL.md priorities. Use Design Context from the current instructions or `.uicraft.md` when available. If high-impact product or brand context is still missing, read [uicraft-init.md](uicraft-init.md) and ask only focused questions; otherwise state conservative assumptions and continue. Additionally establish: the discipline/role being presented (design, engineering, writing, research, hybrid), who the audience is (recruiters skimming, hiring managers deep-diving, clients, collaborators), and whether the design itself should demonstrate skill or stay quiet and let the work speak.

---

## What Makes a Portfolio Different

- **The audience is skimming first, reading second.** Recruiters and hiring managers often spend seconds per site before deciding to go deeper — the first screen must communicate who this person is and what they're good at, fast.
- **Curation beats completeness.** A portfolio with 4 well-presented projects outperforms one with 12 thin entries. Help the user cut, don't just help them add more sections.
- **The work needs a story, not just a gallery.** For case studies, the interesting part is usually the problem and the decisions made — not only the final screenshot.
- **Personality is a feature, within limits.** Unlike most product UI, a portfolio can afford — and often benefits from — a distinct voice and visual signature. But personality should never obscure what the person actually does or make the work harder to evaluate.

## Structural Anatomy

Treat this as a checklist to *consider*, not a mandatory template. What belongs depends heavily on discipline and audience — a case-study-heavy product designer site looks nothing like a minimal writer's site, and both are correct for their context.

- **Intro/hero**: who this person is, what they do, in language specific to them — not a generic "Hi, I'm [Name] 👋" template.
- **Selected work**: the curated project list — depth over breadth; each entry should make the visitor want to click in.
- **Case studies** (if applicable): problem, constraints, process, decisions, outcome — proportion the depth to what's actually interesting, not a rigid template filled out uniformly for every project.
- **About**: background, philosophy, or path — as long or short as it needs to be for the audience.
- **Skills/toolset** (optional, use with restraint): only if it adds real signal beyond what the work already shows.
- **Contact/CTA**: the lowest-friction path to actually reaching this person — email, a form, or a scheduling link, matched to how they actually want to be contacted.
- **Resume/CV link**: for recruiter-facing sites, keep this easy to find, not buried.

## Choose a Style Direction

Pick one direction deliberately based on the discipline and what the visitor needs to evaluate — don't blend all three.

### 1. Quiet Craft

For engineers, researchers, writers, and practitioners whose work should be judged on substance, not visual flourish — the site's job is to get out of the way.

- **Typography**: one excellent type family doing almost everything, strong hierarchy from size/weight alone rather than color or decoration.
- **Color**: near-monochrome with a single restrained accent, used sparingly (links, one highlight per section).
- **Layout**: generous whitespace, a single content column or simple two-column split, minimal chrome.
- **Motion**: little to none — a subtle fade-in at most. Motion here reads as noise, not craft.
- **Signals of quality**: precise writing, real artifacts (papers, repos, articles) linked directly rather than summarized behind a click.

### 2. Maximalist Signature

For designers and other visually-driven creatives where the site itself functions as a work sample — the risk tolerance here is much higher than in product UI.

- **Typography**: expressive, unusual pairings; type can be a graphic element (huge scale, unconventional placement) rather than only a vessel for reading.
- **Color**: a distinctive, personal palette — this is one of the few contexts where a bold or unexpected combination is appropriate rather than a liability.
- **Layout**: unconventional grids, deliberate asymmetry, custom cursor or hover states, layout choices that would be excessive in a product but read as intentional signature here.
- **Motion**: can be a genuine showcase — cursor-following elements, scroll choreography, page-transition treatments — as long as it never blocks access to the work itself and still respects `prefers-reduced-motion`.
- **Signals of quality**: coherence across every micro-decision; a maximalist site that feels considered (not chaotic) is the actual skill being demonstrated.

### 3. Living Case Study

For product designers, PMs, and other practitioners who want to demonstrate process and impact, not just final visuals.

- **Typography**: clean and functional — the UI chrome should feel like a well-designed product, because the site is implicitly a demo of that skill.
- **Color**: a small functional palette (like a real design system) with semantic use — status, progress, before/after states.
- **Layout**: each project reads like an interactive product artifact — tabs or steppers for process phases, before/after comparisons, metrics displayed as real data (only if the numbers are real; never decorative placeholder metrics).
- **Motion**: state-transition-driven — expanding case studies, filterable project lists, progress indicators — motion demonstrates product-thinking, not decoration.
- **Signals of quality**: specific numbers, named constraints, honest tradeoffs — this style fails if the "process" content is vague or generic.

## Portfolio Anti-Patterns

Beyond the general generic-AI tells (see [bolder.md](bolder.md) and [critique.md](critique.md)), watch specifically for:

- Hero with "Hi, I'm [Name] 👋" plus a circular avatar in a gradient-ring frame — instantly recognizable as a template
- A project grid where every card looks identical (same aspect ratio, same hover-zoom, same one-line caption) regardless of how different the projects actually are
- A "skills" section that's a wall of technology logos with no indication of depth or context — logo soup signals breadth-padding, not competence
- Case studies that follow "Problem / Solution / Result" so rigidly and vaguely that they could describe any project ("The problem was users were confused. The solution was a redesign. The result was improved metrics.")
- A boilerplate closing CTA ("Let's build something amazing together!") that doesn't specify what kind of work or collaboration the person actually wants
- Decorative metrics or stats presented as real data ("300% improvement") without context or source — undermines credibility more than it builds it

## Content & UX Considerations

- Write case study depth to match actual interest — the most senior audience wants to see judgment and tradeoffs, not a polished-sounding summary.
- Optimize images/video aggressively; portfolio sites are often visually heavy and slow load directly undermines the craft they're trying to demonstrate (see [optimize.md](optimize.md)).
- Make the contact path match the actual intent — a recruiter wants a resume link and email; a prospective client wants to understand availability and process; don't force everyone through the same generic contact form.
- If the person's name and current role/availability aren't obvious within the first screen, fix that before anything else — it's the single most common failure mode for portfolio first impressions.

## Verify

- Would a recruiter skimming for 10 seconds understand who this person is and what they're best at?
- Does the curated project list actually represent the strongest work, or just all available work?
- Does the chosen style direction match what this discipline's audience actually values (a backend engineer's audience rewards substance over visual flair; a designer's audience expects visual flair as part of the evidence)?
- Run the standard [critique.md](critique.md) generic-AI check before shipping.
