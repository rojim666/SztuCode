---
name: delight
description: Give an interface personality, surprise, and small joyful touches so it is remembered rather than merely used. Turns the merely functional into something people enjoy. Use when the user asks for polish, character, animation, micro-interactions, delight, or wants an interface that feels fun or memorable.
---

## Contents

- [Required Preparation](#required-preparation)
- [Find the Moments Worth Delighting](#find-the-moments-worth-delighting)
- [Ground Rules](#ground-rules)
- [The Delight Toolkit](#the-delight-toolkit)
- [Tooling and Budget](#tooling-and-budget)
- [Check Your Work](#check-your-work)


Hunt for the places where a little joy, character, or unexpected craft turns a working interface into one people actually enjoy.

## Required Preparation

Do not skip this. Start from the priorities in the main SKILL.md, and pull Design Context from the current instructions or from `.uicraft.md` if either supplies it. Should important product or brand context still be missing, consult [uicraft-init.md](uicraft-init.md) and ask a small number of targeted questions — otherwise write down conservative assumptions and keep going. One extra thing to establish here: the register the domain calls for, somewhere on the spectrum of playful, professional, quirky, and elegant.

---

## Find the Moments Worth Delighting

Look for spots where delight adds to the experience instead of pulling attention away from it.

1. **Where delight naturally lives**:
   - **Completion**: an action that landed — saved, sent, published
   - **Emptiness**: blank slates, first runs, onboarding
   - **Waiting**: dead time that could be worth watching
   - **Progress**: milestones, streaks, things finished
   - **Touch points**: hovers, clicks, drags
   - **Failure**: taking the sting out of a frustrating moment
   - **Secrets**: things only a curious user will find

2. **Read the situation**:
   - How does the brand carry itself — playful, professional, quirky, elegant?
   - Who is on the other end — technical users, creatives, corporate staff?
   - What is the user feeling right now — accomplished, exploratory, frustrated?
   - What would land badly here? A banking app is not a gaming app.

3. **Choose a direction**:
   - **Quiet refinement**: micro-interactions with precision, the register of luxury brands
   - **Open playfulness**: whimsical illustration and copy, at home in consumer apps
   - **Useful anticipation**: solving the next need before it is voiced, ideal for productivity tools
   - **Sensory depth**: gratifying sound and fluid animation, natural in creative tools

Anything you cannot infer from the codebase, put to the user as a direct question.

**CRITICAL**: usability comes first and delight serves it. The moment users are paying more attention to your flourish than to the thing they came to do, the flourish has overshot.

## Ground Rules

Four constraints shape everything below.

### It Adds, It Never Obstructs
- Keep any single delight moment under a second
- Core functionality never waits on a flourish
- Let people skip past it, or keep it quiet enough to ignore
- The user's time and concentration outrank your animation

### Let People Find It
- Bury some of the good parts for users to stumble onto
- Pay off curiosity and exploration
- Resist narrating every touch you added
- Give users something worth telling someone else about

### Fit the Moment
- Tune the emotional register: celebrate wins, show empathy on failures
- Read the user's state — nobody wants jokes during a critical error
- Stay inside the brand's personality and the audience's expectations
- Remember that delight is culturally specific; what charms in one market lands oddly in another

### Survive Repetition
- What delighted on day one should still work on day thirty
- Rotate responses instead of replaying one animation forever
- Open up further layers as usage deepens
- Use recognizable patterns to build anticipation

## The Delight Toolkit

Concrete ways to put character into an interface.

### Motion and Micro-interactions

**Buttons worth pressing**:
```css
/* A press with physical weight */
.cta {
  transition: transform 0.1s, box-shadow 0.1s;
}
.cta:active {
  transform: translateY(2px);
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

/* Ripple spreading from the click point */
/* Rising toward the cursor */
.cta:hover {
  transform: translateY(-2px);
  transition: transform 0.2s cubic-bezier(0.25, 1, 0.5, 1); /* ease-out-quart */
}
```

**Waiting with character**:
- Loading animations with an idea behind them, not another spinner
- Loading copy in your own voice — write lines specific to the product, never generic AI filler
- Progress readouts paired with encouragement
- Skeleton screens carrying a light animation

**Confirming success**:
- A checkmark that draws itself
- Confetti when the milestone deserves it
- A soft scale-and-fade to acknowledge the action
- A quiet, satisfying sound

**Rewarding hover**:
- Icons that come alive under the pointer
- Shifts in color, or a glow
- Tooltips that say something with personality
- Custom cursors where the brand supports it

### Voice in the Copy

**Errors that soften the blow**:
```
Flat:    "Error 404"
Better:  "We looked everywhere. This page is not where it claimed to be."

Flat:    "Connection failed"
Better:  "The network stepped out for a moment. Want to try again?"
```

**Empty states that invite action**:
```
Flat:    "No projects"
Better:  "A blank canvas. Go make something."

Flat:    "No messages"
Better:  "Inbox at zero. Today is going well."
```

**Labels and tooltips with a wink**:
```
Flat:    "Delete"
Better:  "Send to the void"    (only where the brand can carry it)

Flat:    "Help"
Better:  "Rescue me"           (as a tooltip)
```

**IMPORTANT**: the voice has to belong to the brand. A bank has no business being zany, though nothing stops it from being warm.

### Drawing and Visual Character

**Illustration**:
- Empty states drawn on purpose, rather than a stock icon
- Error screens with a face on them — an approachable creature, an odd little character
- Loading art with animated characters
- Success art that reads as a celebration

**Icons with a point of view**:
- A custom set tuned to the brand's personality
- Small motion on hover or click
- More illustrative and detailed than the generic default
- One consistent style across the whole set

**Depth in the background**:
- Restrained particle effects
- Gradient mesh fields
- Geometric pattern work
- Parallax layering
- Themes that follow the hour — morning against night

### Interactions That Feel Good

**Dragging and dropping**:
- The item lifts as you grab it, with shadow and scale
- It snaps into place on release
- A placement sound that satisfies
- An undo path: "Dropped in wrong place? [Undo]"

**Toggles**:
- A slide governed by spring physics
- Color moving with the state
- Haptics on mobile hardware
- An optional sound

**Progress and achievement**:
- Streak counters that make a moment of the milestones
- Progress bars that mark hitting 100%
- Badges unlocking with animation
- Stats with attitude: "You're on fire! 5 days in a row"

**Forms**:
- Inputs that animate as focus arrives
- Checkboxes that pulse with a scale on check
- A success state that acknowledges valid input
- Textareas that grow with their content

### Audio

**Quiet cues, where they suit the product**:
- Notification tones that are recognizable without being irritating
- A gratifying "ding" on success
- Error sounds that sympathize rather than scold
- Keystroke sounds in chat and messaging contexts
- Ambient beds, kept very low

**IMPORTANT**:
- Defer to the operating system's sound settings
- Always offer a mute
- Keep the level low — these are cues, not alarms
- Do not fire on every interaction; sound fatigue is a real thing

### Hidden Layers

**Things to discover**:
- A Konami code that unlocks an alternate theme
- Undocumented shortcuts, e.g. Cmd+K reaching special features
- Logos and illustrations that respond to hover
- Jokes tucked into alt text — screen reader users deserve them too
- A message in the console for developers: "Like what you see? We're hiring!"

**Marking the calendar**:
- Holiday treatments, kept subtle and tasteful
- Palettes that drift with the season
- Variations that follow the weather
- Shifts by hour: dark after dark, light by day

**Responding to context**:
- Copy that changes with the time of day
- Reactions tied to particular user actions
- Randomized variants so nothing repeats identically
- Layers that unfold the longer someone stays

### Turning Waits Into Something

**Make the wait worth sitting through**:
- A rotating set of interesting loading lines
- Progress bars with a voice
- A small game to play through a long load
- Tips or facts served while things load
- A countdown with encouragement attached

```
Write loading lines that describe your actual product — not generic AI filler:
- "Adding up this month's numbers..."
- "Pulling in what your team changed..."
- "Laying out your dashboard..."
- "Checking what's new since yesterday..."
```

**WARNING**: stay away from the worn-out loading joke — "Herding pixels", "Teaching robots to dance", "Consulting the magic 8-ball", "Counting backwards from infinity". Lines like these read as machine-written the instant anyone sees them. Say something only your product could say.

### Marking Milestones

**Celebrating a win**:
- Confetti reserved for milestones that earn it
- Checkmarks that animate on completion
- A flourish when a progress bar reaches 100%
- Notifications framed as "achievement unlocked"
- Messages that know the user: "You published your 10th article!"

**Recognizing the journey**:
- Treat first-time actions as special
- Track streaks and mark them
- Show movement toward a goal
- Notice anniversaries

## Tooling and Budget

**For animation**:
- Framer Motion (React)
- GSAP (universal)
- Lottie (After Effects animations)
- Canvas confetti (party effects)

**For sound**:
- Howler.js (audio management)
- Use-sound (React hook)

**For physics**:
- React Spring (spring physics)
- Popmotion (animation primitives)

**IMPORTANT**: weight counts. Compress your images, tighten your animations, and load delight features lazily.

**Things that ruin it**:
- Making core functionality wait on a flourish
- Trapping users inside a delightful moment instead of letting them skip it
- Papering over bad UX with charm
- Piling it on — restraint reads as confidence
- Treating accessibility as optional: animate responsibly and offer alternatives
- Delighting at every single interaction, which drains the special moments of meaning
- Paying for delight with performance
- Misjudging the room and shipping something that does not fit the context

## Check Your Work

Confirm the delight actually delights:

- **Reaction**: do people smile, and do they screenshot it?
- **Wear**: is it still pleasant on the hundredth encounter?
- **Escape hatch**: can it be skipped or turned off?
- **Smoothness**: no jank, no slowdown
- **Fit**: consistent with brand and context
- **Reach**: holds up under reduced motion and with a screen reader

Delight is what separates a tool from an experience: character, a positive surprise, moments people want to pass along. It only works while usability stays intact — the flourish serves the task, never the other way around.
