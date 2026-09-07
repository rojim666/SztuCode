---
name: uicraft-init
description: One-time bootstrap that captures a project's design context and writes it to a persistent config file, so later sessions inherit the same direction instead of re-deriving it. Run once per project.
---

Build a durable picture of what this project is trying to look and feel like, then commit it to disk so every future session starts from it.

## Step 1: Mine the repository first

Questions are expensive; evidence is free. Read the project before you ask the user anything.

Look for:

- **README and documentation** — what the product is for, who it serves, what it claims to optimize for
- **`package.json` and config files** — the stack, the dependencies, any UI or design library already in play
- **Components already written** — the spacing, type, and composition habits currently in force
- **Brand material** — logos, favicons, hard-coded brand colors
- **Tokens and CSS custom properties** — palettes, font stacks, spacing scales that already exist
- **Style guides or brand docs**, if the project keeps any

Then take stock: write down what the codebase told you, and what it could not.

## Step 2: Ask only about what code cannot reveal

Implementation details expose constraints and conventions. They do not expose intent. Ask the user only where the answer is high-impact and genuinely absent from the evidence — and skip anything Step 1 already settled.

**On the people and the job**

- Who reaches for this, and under what circumstances?
- What are they actually trying to accomplish?
- What should the interface make them feel — confidence, calm, delight, urgency, something else?

**On brand and character**

- Three words for the brand's personality?
- Any products or sites that hit the right note, and what specifically about them lands?
- Anti-references: what should this deliberately not resemble?

**On visual preference**

- Is there a direction you already lean toward — minimal, bold, elegant, playful, technical, organic?
- Light theme, dark theme, or both?
- Colors that are mandatory, and colors that are off-limits?

**On accessibility and inclusion**

- Any accessibility bar to hit, such as a specific WCAG level or a known user need?
- Accommodations to plan for, such as reduced motion or color vision deficiency?

## Step 3: Persist the result

Fold the evidence and the answers together into a `## Design Context` section:

```markdown
## Design Context

### Users
[Who they are, their context, the job to be done]

### Brand Personality
[Voice, tone, 3-word personality, emotional goals]

### Aesthetic Direction
[Visual tone, references, anti-references, theme]

### Design Principles
[3-5 principles derived from the conversation that should guide all design decisions]
```

Save it to `.uicraft.md` at the project root. When that file already exists, edit the Design Context section in place rather than appending a second copy.

Do not spray this into other AI configuration files. Copy it into something like `AGENTS.md` only on explicit request; otherwise leave every other config file untouched.

Finish by confirming what was written and restating the design principles that will now govern the work.
