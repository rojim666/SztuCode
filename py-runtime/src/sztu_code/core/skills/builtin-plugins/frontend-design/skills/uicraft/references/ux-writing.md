---
name: UX Writing
description: Interface copy craft — naming actions on buttons, wording failures, filling empty screens, onboarding text, microcopy conventions, and holding a consistent voice and tone.
---

## Contents

- [Naming Actions on Buttons](#naming-actions-on-buttons)
- [Errors That Actually Help](#errors-that-actually-help)
- [Turning Empty Screens Into Openings](#turning-empty-screens-into-openings)
- [Progress Messages and Confirmations](#progress-messages-and-confirmations)
- [Text Inside Forms](#text-inside-forms)
- [One Voice, Shifting Tone](#one-voice-shifting-tone)
- [Say One Thing One Way](#say-one-thing-one-way)
- [Cut Copy That Repeats Itself](#cut-copy-that-repeats-itself)
- [Copy Screen Readers Can Use](#copy-screen-readers-can-use)
- [Copy That Survives Localization](#copy-that-survives-localization)


# UX Writing

## Naming Actions on Buttons

**"OK", "Submit", and a bare "Yes"/"No" pair are non-answers** — they make the reader infer the outcome. Name the verb and its object instead:

| Lazy label | Rewrite | What the rewrite buys |
|-----|------|-----|
| OK | Save changes | The reader knows the result before clicking |
| Submit | Create account | Frames the outcome, not the mechanism |
| Yes | Delete message | Restates the action being agreed to |
| Cancel | Keep editing | Removes the ambiguity in "cancel" |
| Click here | Download PDF | Names where the link goes |

Destructive controls should name what gets destroyed. Prefer "Delete" over "Remove" — deletion reads as permanent, removal implies recoverable. And quantify the blast radius: "Delete 5 items" beats "Delete selected".

## Errors That Actually Help

A usable error answers three questions: what broke, why, and what to do next. "Email address isn't valid. Please include an @ symbol." carries all three; "Invalid input" carries none.

Reach for these shapes:

| Failure | Shape of the message |
|-----------|----------|
| **Wrong format** | "[Field] needs to be [format]. Example: [example]" |
| **Left blank** | "Please enter [what's missing]" |
| **Not authorized** | "You don't have access to [thing]. [What to do instead]" |
| **Connection failed** | "We couldn't reach [thing]. Check your connection and [action]." |
| **Backend fault** | "Something went wrong on our end. We're looking into it. [Alternative action]" |

Point the sentence at the field, never at the person: "Please enter a date in MM/DD/YYYY format", not "You entered an invalid date".

## Turning Empty Screens Into Openings

An empty state is an onboarding surface in disguise. Acknowledge the emptiness briefly, say what filling it is worth, and hand over one obvious action. "No projects yet. Create your first one to get started." does the job; a lone "No items" throws it away.

## Progress Messages and Confirmations

While something runs, name the specific thing: "Saving your draft..." rather than a generic "Loading...". For long waits, set the expectation ("This usually takes 30 seconds") or show real progress.

Most confirmation dialogs are a symptom of a missing undo — an undoable action needs no gate. When one is genuinely warranted, name the action, state the consequence, and label both buttons concretely: "Delete project" and "Keep project", never "Yes" and "No".

## Text Inside Forms

Show the expected format in the placeholder rather than writing a sentence about it. When a field's purpose isn't self-evident, say why you need the data.

## One Voice, Shifting Tone

**Voice** is the brand's personality and does not move. **Tone** is how that voice adjusts to the moment:

| Moment | How the tone bends |
|--------|------------|
| Success | Short and celebratory: "Done! Your changes are live." |
| Error | Empathetic and practical: "That didn't work. Here's what to try..." |
| Loading | Steadying: "Saving your work..." |
| Destructive confirm | Sober and unambiguous: "Delete this project? This can't be undone." |

Keep jokes out of failure states entirely. The reader is already frustrated; be helpful, not cute.

## Say One Thing One Way

Settle on a single term per concept and never rotate through synonyms:

| Drifting | Settled |
|--------------|------------|
| Delete / Remove / Trash | Delete |
| Settings / Preferences / Options | Settings |
| Sign in / Log in / Enter | Sign in |
| Create / Add / New | Create |

Maintain a glossary and hold the product to it. Synonyms feel like variety to the writer and like new concepts to the reader.

## Cut Copy That Repeats Itself

An intro that restates the heading is dead weight, and a self-explanatory button needs no caption. Say it once, say it well.

## Copy Screen Readers Can Use

Link text must make sense read out of context — "View pricing plans", not "Click here". Alt text carries the information, not the picture: "Revenue increased 40% in Q4" beats "Chart", and decorative images take `alt=""`. Icon-only buttons need an `aria-label` to announce themselves.

## Copy That Survives Localization

Translations rarely match the English footprint — German typically runs ~30% longer — so leave room:

| Language | Length change |
|----------|-----------|
| German | +30% |
| French | +20% |
| Finnish | +30-40% |
| Chinese | -30% (fewer characters, comparable width) |

Four habits keep strings translatable. Hold numbers outside the sentence ("New messages: 3", not "You have 3 new messages"). Store whole sentences instead of concatenating fragments, since word order shifts by language. Spell words out — "5 minutes ago", not "5 mins ago". Ship context notes telling translators where each string appears.

---

**Steer clear of**: unexplained jargon; copy that assigns fault to the reader ("You made an error" should read "This field is required"); catch-all failures like "Something went wrong"; swapping terminology around for freshness; and humor anywhere near an error.
