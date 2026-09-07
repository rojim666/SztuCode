---
name: clarify
description: Rewrites murky interface text — error messages, microcopy, labels, instructions — so people can actually follow it. Use when the user mentions confusing wording, unclear labels, bad error messages, instructions that are hard to follow, or a desire for better UX writing.
---

## Contents

- [Groundwork You Cannot Skip](#groundwork-you-cannot-skip)
- [Diagnose the Existing Text](#diagnose-the-existing-text)
- [Decide What the Copy Must Do](#decide-what-the-copy-must-do)
- [Rewrite Surface by Surface](#rewrite-surface-by-surface)
- [Rules Every Line Obeys](#rules-every-line-obeys)
- [Check That It Landed](#check-that-it-landed)


Hunt down interface text that is vague, confusing, or simply badly written, and rewrite it so the product becomes easier to grasp and to operate.

## Groundwork You Cannot Skip

Begin from the priorities in the main SKILL.md. Take Design Context from the current instructions, or from `.uicraft.md` if that file is present. If product or brand context that would materially shift your wording is still unknown, read [uicraft-init.md](uicraft-init.md) and ask a tight set of questions; otherwise say plainly what conservative assumptions you are making and carry on. Two extra inputs matter here: how technical the audience is, and the mental state users are in at this point in the flow.

---

## Diagnose the Existing Text

Work out precisely why the current wording fails.

**Symptoms to look for:**

- **Jargon** — vocabulary the reader has no reason to know
- **Ambiguity** — a sentence that supports more than one reading
- **Passive constructions** — "Your file has been uploaded" where "We uploaded your file" is available
- **Wrong length** — padded out, or clipped so far it stops making sense
- **Unearned assumptions** — knowledge the user was never given
- **Absent context** — nothing tells the reader what to do or why it matters
- **Tone mismatch** — stiff, breezy, or otherwise wrong for the moment

**Context to establish:**

- Who is reading this — engineers, a general audience, someone on day one?
- What emotional state are they in — rattled by an error, or riding a success?
- What behavior is this text supposed to produce?
- What boundaries apply — character caps, available space?

**CRITICAL**: Copy that reads clearly is how people succeed. Copy that does not generates frustration, mistakes, and a queue of support tickets.

## Decide What the Copy Must Do

Set the strategy before drafting:

- **The single message**: what is the one fact the reader must walk away with?
- **The next move**: what, if anything, should they do?
- **The feeling**: helpful, apologetic, encouraging — pick one
- **The limits**: length ceilings, brand voice, whatever localization demands

**IMPORTANT**: UX writing works best when nobody notices it. The reader should absorb the meaning without ever registering the sentence.

## Rewrite Surface by Surface

Each of these surfaces has its own failure pattern.

### Error Messages

**Weak**: "Error 403: Forbidden"
**Better**: "You don't have permission to open this workspace. Ask an owner to grant you access."

**Weak**: "Invalid input"
**Better**: "Phone numbers need a country code. Try: +1 415 555 0142"

Rules of thumb:
- Say what broke, in ordinary language
- Hand the reader a fix
- Keep the blame off the user
- Show an example where one clarifies things
- Point to help or support when that route exists

### Form Labels and Instructions

**Weak**: "Exp. (MM/YY)"
**Better**: "Card expiry date" — with the format carried by the placeholder

**Weak**: "Enter value here"
**Better**: "Your work email" or "Team name"

Rules of thumb:
- Label things precisely; do not let a generic placeholder stand in for a label
- Demonstrate the expected format with an example
- Say why you are asking whenever the reason is not self-evident
- Position guidance above the field, never below it
- Mark required fields unambiguously

### Buttons and Calls to Action

**Weak**: "Click here" | "Submit" | "OK"
**Better**: "Create account" | "Publish post" | "Got it, thanks"

Rules of thumb:
- Name the action the button performs
- Write in the active voice — a verb paired with a noun
- Mirror how the user already thinks about the task
- Choose the concrete word: "Publish" carries more than "OK"

### Help Text and Tooltips

**Weak**: "This is the workspace URL field"
**Better**: "Pick a workspace URL. You can rename it later in Settings."

Rules of thumb:
- Contribute something the label did not already say
- Answer the question actually forming in the reader's head — what is this, or why do you want it
- Stay short without going incomplete
- Link out to full documentation when depth is warranted

### Empty States

**Weak**: "No items"
**Better**: "No invoices yet. Create your first one to get started."

Rules of thumb:
- Account for the emptiness when the reason is not obvious
- Make the next action unmistakable
- Read as an invitation, not a dead end

### Success Messages

**Weak**: "Success"
**Better**: "Profile updated. The new details are live right away."

Rules of thumb:
- State what actually happened
- Cover what comes next when that is relevant
- Stay short without going incomplete
- Meet the emotional register of the moment — a genuine milestone deserves a genuine celebration

### Loading States

**Weak**: "Loading..." sitting there for 30 seconds or more
**Better**: "Importing your contacts... this usually takes 30-60 seconds"

Rules of thumb:
- Tell the reader roughly how long
- Explain the work in progress when it is not self-evident
- Surface real progress wherever you can measure it
- Provide a way out — a "Cancel" — where that makes sense

### Confirmation Dialogs

**Weak**: "Are you sure?"
**Better**: "Delete 'Q4 Budget'? This can't be undone."

Rules of thumb:
- Name the exact operation being confirmed
- Spell out what follows, especially when the action destroys something
- Label the buttons with the action: "Delete file" beats "Yes"
- Reserve confirmations for genuinely risky moves; asking constantly trains people to click through

### Navigation and Wayfinding

**Weak**: Vague labels — "Items" | "Things" | "Stuff"
**Better**: Concrete labels — "Your invoices" | "Teammates" | "Settings"

Rules of thumb:
- Name destinations specifically and descriptively
- Use the audience's vocabulary, not internal shorthand
- Make the structure legible
- Preserve information scent through breadcrumbs and a visible sense of where the user is

## Rules Every Line Obeys

1. **Specific**: "Enter email", never "Enter value"
2. **Concise**: strip filler, but not at the cost of meaning
3. **Active**: "Save changes", never "Changes will be saved"
4. **Human**: "Oops, something went wrong" over "System error encountered"
5. **Helpful**: describe the next action, not merely the event
6. **Consistent**: settle on one term and reuse it; variety is a virtue in prose, not in interfaces

**Practices to avoid:** dropping jargon in without a gloss; pinning fault on the reader, so recast "You made an error" as "This field is required"; vagueness such as a bare "Something went wrong"; passive voice where the active form was available; explanations that run long past their point; jokes attached to failures, where empathy is what is called for; presuming technical fluency; letting terminology drift from screen to screen; saying the same thing twice, whether that is a heading restating the intro or a redundant explanation; and leaning on placeholders as the only label, since they vanish the instant someone starts typing.

## Check That It Landed

Interrogate the rewrite:

- **Comprehension**: does it stand on its own, with no surrounding explanation?
- **Actionability**: is the next step obvious?
- **Brevity**: could it be shorter and still be clear?
- **Consistency**: does the vocabulary match the rest of the product?
- **Tone**: does it suit this particular moment?

Approach this as a communication specialist would: write as though explaining the product to a sharp friend who has never seen it. Clear, useful, and recognizably human.
