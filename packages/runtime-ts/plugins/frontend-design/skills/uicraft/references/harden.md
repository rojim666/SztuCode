---
name: harden
description: Toughens an interface so it survives contact with reality — error paths, translated text, overflowing content, and every awkward edge case. Use when the user asks to harden, make production-ready, handle edge cases, add error states, or fix overflow and i18n issues.
---

## Contents

- [Find the Weak Points](#find-the-weak-points)
- [Where to Add Resilience](#where-to-add-resilience)
- [How to Test](#how-to-test)
- [Prove It Holds](#prove-it-holds)


Reinforce an interface against the things that break idealized designs: hostile inputs, failing requests, translated copy, and the messy ways real people actually use software.

## Find the Weak Points

Go looking for the cracks before users do.

1. **Push the inputs to their extremes**:
   - text far longer than expected — names, titles, descriptions
   - text that barely exists — a single character, or nothing at all
   - awkward characters — emoji, right-to-left script, accented letters
   - numbers in the millions and billions
   - collections at scale — lists past 1000 rows, selects past 50 options
   - the total absence of data, i.e. empty states

2. **Walk the failure paths**:
   - the network dropping, crawling, or timing out
   - API responses of 400, 401, 403, 404, and 500
   - validation rejections
   - permission denials
   - rate limits kicking in
   - two operations racing each other

3. **Run it in other languages**:
   - translations that run long — German typically expands about 30% beyond English
   - RTL scripts such as Arabic and Hebrew
   - character sets spanning Chinese, Japanese, Korean, and emoji
   - date and time conventions
   - number formatting, where 1,000 and 1.000 mean the same thing
   - currency symbols

**CRITICAL**: An interface that only holds together when the data is perfect is not ready to ship. Build for reality instead.

## Where to Add Resilience

Take the dimensions below one at a time.

### Text That Does Not Fit

**Containing long strings**:
```css
/* Clip to one line and mark the cut */
.headline-clip {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Cap at a fixed number of lines */
.excerpt-clip {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Let long words break rather than escape the box */
.prose-block {
  word-wrap: break-word;
  overflow-wrap: break-word;
  hyphens: auto;
}
```

**Keeping flex and grid children in bounds**:
```css
/* Flex children refuse to shrink past their content without this */
.row-cell {
  min-width: 0;
  overflow: hidden;
}

/* Same story for grid tracks, on both axes */
.grid-cell {
  min-width: 0;
  min-height: 0;
}
```

**Sizing text responsively**:
- reach for `clamp()` when type should scale fluidly
- hold a readable floor — nothing under 14px on mobile
- verify the layout at 200% browser zoom
- make sure containers grow as their text grows

### Speaking Other Languages

**Budget for expansion**:
- leave 30-40% headroom for translated strings
- lay things out with flexbox or grid so they respond to content length
- sanity-check against the longest language you support, which is usually German
- never pin a fixed width onto a container holding text

```jsx
// ❌ Sized around one short English word
<button className="w-28">Checkout</button>

// ✅ Padding lets the label determine the width
<button className="px-4 py-2">Checkout</button>
```

**Supporting right-to-left**:
```css
/* Logical properties flip automatically */
margin-inline-start: 1rem; /* in place of margin-left */
padding-inline: 1rem; /* in place of padding-left/right */
border-inline-end: 1px solid; /* in place of border-right */

/* Where direction has to be handled explicitly */
[dir="rtl"] .chevron { transform: scaleX(-1); }
```

**Handling character sets**:
- keep UTF-8 in place end to end
- exercise the UI with CJK — Chinese, Japanese, Korean
- exercise it with emoji as well, since a single glyph can occupy 2-4 bytes
- expect other scripts too: Latin, Cyrillic, Arabic, and beyond

**Formatting dates, times, and numbers**:
```javascript
// ✅ Delegate locale rules to the Intl API
new Intl.DateTimeFormat('en-US').format(date); // 1/15/2024
new Intl.DateTimeFormat('de-DE').format(date); // 15.1.2024

new Intl.NumberFormat('en-US', { 
  style: 'currency', 
  currency: 'USD' 
}).format(1234.56); // $1,234.56
```

**Getting plurals right**:
```javascript
// ❌ Hard-codes English plural rules
`${count} file${count !== 1 ? 's' : ''}`

// ✅ Hand it to the i18n layer
t('files', { count }) // Handles complex plural rules
```

### When Things Go Wrong

**Network failures**:
- state the problem in plain language
- give people a way to retry
- say what actually happened
- fall back to an offline mode where that makes sense
- account for requests that simply never return

```jsx
// Failure surfaced with a path back out
{loadError && (
  <ErrorPanel>
    <p>We couldn't load your workspace. {loadError.message}</p>
    <button onClick={reload}>Retry</button>
  </ErrorPanel>
)}
```

**Rejected form input**:
- render each error beside the field it belongs to
- be specific about what is wrong
- point toward the fix
- avoid blocking submission when you do not have to
- keep everything the user already typed

**API status codes**, each with its own response:
- 400: surface the validation detail
- 401: send them to sign in
- 403: explain the permission gap
- 404: render a not-found state
- 429: tell them a rate limit was hit
- 500: show a general failure and route them to support

**Degrading gracefully**:
- the core flow should still function with JavaScript unavailable
- every image carries alt text
- layer enhancements on top of a working baseline
- provide fallbacks wherever a feature may be unsupported

### Boundary Conditions

**Nothing to show**:
- a list with no rows
- a search returning no matches
- an empty notification tray
- any view with no data behind it
- always paired with an obvious next step

**Work in progress**:
- the first load
- loading another page of results
- refreshing existing data
- name what is loading — "Loading your projects..."
- estimate the wait when an operation is genuinely slow

**Data at volume**:
- paginate, or virtualize the scroll
- offer search and filtering
- tune the rendering path
- never pull all 10,000 records down at once

**Overlapping actions**:
- disable the button while a request is in flight so nothing submits twice
- expect race conditions and handle them
- pair optimistic updates with a rollback
- resolve conflicts deliberately

**Restricted access**:
- viewing is not permitted
- editing is not permitted
- read-only presentation
- and in each case, a clear explanation of why

**Older browsers**:
- polyfill the modern APIs you rely on
- supply fallbacks for CSS that may not be supported
- detect features, never user agents
- run the suite against the browsers you actually target

### Accessibility Under Stress

**Keyboard operation**:
- everything achievable with a mouse must be achievable without one
- tab order should follow the visual order
- modals need their focus explicitly managed
- long pages need skip links

**Screen readers**:
- label controls properly with ARIA
- announce content that changes on the fly through live regions
- write alt text that actually describes
- start from semantic HTML

**Reduced motion**:
```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

**High contrast**:
- check the interface in Windows high contrast mode
- never let color be the only carrier of meaning
- back it up with a second visual cue

### Input Constraints and Sanitization

**In the browser**:
- mark what is required
- validate formats such as email, phone, and URL
- enforce length ceilings
- match against patterns
- add whatever domain rules the field needs

**On the server, without exception**:
- client-side checks are a convenience, never a guarantee
- validate and sanitize every incoming value
- close off injection vectors
- apply rate limiting

**Expressing limits in the markup**:
```html
<!-- Constraints stated up front, and described to assistive tech -->
<input 
  type="text"
  maxlength="100"
  pattern="[A-Za-z0-9]+"
  required
  aria-describedby="handle-hint"
/>
<small id="handle-hint">
  Letters and numbers only, up to 100 characters
</small>
```

### Performance Under Bad Conditions

**Thin bandwidth**:
- load images progressively
- hold the layout with skeleton screens
- update the UI optimistically
- support offline use through service workers

**Leaks**:
- tear down event listeners
- unsubscribe from anything you subscribed to
- clear timers and intervals
- abort in-flight requests when the component unmounts

**Rate-limiting your own handlers**:
```javascript
// Wait for typing to settle before querying
const deferredQuery = debounce(runQuery, 300);

// Cap how often scroll work runs
const cappedScroll = throttle(onScrollUpdate, 100);
```

## How to Test

**By hand**:
- feed it extreme data — enormous, minimal, absent
- switch languages
- pull the network cable
- throttle down to 3G
- drive it with a screen reader
- put the mouse away and use only the keyboard
- open it in the older browsers you support

**Automated**:
- unit tests aimed squarely at edge cases
- integration tests covering the failure paths
- end-to-end tests over the critical journeys
- visual regression coverage
- accessibility scans with axe or WAVE

**IMPORTANT**: Hardening means planning for what you did not think of. Whatever you consider unlikely, some user will do on their first afternoon.

A hardened interface never does the following. It never assumes input arrives well-formed — everything gets validated. It never treats internationalization as optional, because the audience is global. It never settles for a message like "Error occurred" when it could say something useful. It never overlooks the offline case. It never leans on client-side validation as the only line of defense. It never hard-codes widths around text, nor sizes anything on the assumption that English lengths apply. And it never takes the whole screen down because one component failed.

## Prove It Holds

Put the finished work through these deliberately:

- **Overlong text**: enter a name of 100+ characters
- **Emoji**: drop emoji into every text field there is
- **RTL**: run through it in Arabic or Hebrew
- **CJK**: run through it again in Chinese, Japanese, or Korean
- **Connectivity**: cut the network, then throttle it
- **Volume**: load it up with 1000+ items
- **Rapid repeats**: hammer the submit button ten times in a row
- **Failures**: force API errors and walk every error state
- **Emptiness**: strip all the data out and inspect the empty states

The target is production, not the demo. People will paste in strange data, lose their connection halfway through a flow, and use the product in ways nobody sketched out. Every component should be built to absorb that.
