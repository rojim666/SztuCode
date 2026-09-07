---
name: optimize
description: Finds and repairs UI performance problems — load speed, rendering, animation smoothness, images, and bundle weight. Use when the user reports something slow, laggy, or janky, raises bundle size or load time, or asks for a faster, smoother experience.
---

## Contents

- [Diagnose Before You Touch Anything](#diagnose-before-you-touch-anything)
- [Where the Wins Are](#where-the-wins-are)
- [Hitting the Core Web Vitals Thresholds](#hitting-the-core-web-vitals-thresholds)
- [Instrumentation](#instrumentation)
- [Confirm the Win](#confirm-the-win)


Track down what is making the interface slow, fix it, and leave the experience faster and smoother than you found it.

## Diagnose Before You Touch Anything

Establish where performance actually stands and what is dragging it down.

1. **Take the baseline**:
   - **Core Web Vitals**: field data for LCP, INP, and CLS as they stand today
   - **Load timing**: first contentful paint through to time to interactive
   - **Payload weight**: how much JavaScript, CSS, and imagery ships
   - **Runtime behavior**: frames per second, memory footprint, CPU load
   - **Network shape**: how many requests, how large, and in what waterfall order

2. **Locate the bottleneck**:
   - Which part is slow — the first load, the interactions, or the animation?
   - What is behind it — oversized images, costly JavaScript, layout thrashing?
   - How severe is it — barely perceivable, actively annoying, or outright blocking?
   - Who feels it — everyone, mobile users only, or people on poor connections?

**CRITICAL**: take a measurement before the change and another after. Optimizing on a hunch burns time; spend it where the numbers say it matters.

## Where the Wins Are

Work through these in a deliberate order rather than opportunistically.

### Load Performance

**Images**:
- Ship modern formats — WebP, AVIF
- Serve the right dimensions; a 300px slot does not need a 3000px file
- Defer anything below the fold with lazy loading
- Adapt to the viewport using `srcset` and the `picture` element
- Compress — at 80-85% quality the loss is usually invisible
- Put a CDN in front of delivery

```html
<img 
  src="banner.webp"
  srcset="banner-400.webp 400w, banner-800.webp 800w, banner-1200.webp 1200w"
  sizes="(max-width: 400px) 400px, (max-width: 800px) 800px, 1200px"
  loading="lazy"
  alt="Product banner"
/>
```

**JavaScript weight**:
- Split the bundle by route and by component
- Let tree shaking drop code nothing references
- Uninstall dependencies you no longer use
- Push non-critical code out of the initial payload
- Pull large components in through dynamic imports

```javascript
// Deferred until the chart is actually rendered
const RevenueChart = lazy(() => import('./RevenueChart'));
```

**CSS**:
- Strip rules nothing matches
- Inline what is needed for first paint; load the remainder asynchronously
- Minify the stylesheets
- Apply CSS containment to regions that render independently

**Fonts**:
- Set `font-display` to `swap` or `optional`
- Subset the file down to the characters you actually render
- Preload the faces needed for first paint
- Fall back to system fonts where the design allows it
- Keep the number of loaded weights small

```css
@font-face {
  font-family: 'EditorialSans';
  src: url('/assets/editorial-sans.woff2') format('woff2');
  font-display: swap; /* Paint the fallback right away */
  unicode-range: U+0020-007F; /* Restrict to Basic Latin */
}
```

**Delivery strategy**:
- Send critical resources first, and mark the rest `async` or `defer`
- Preload the assets the first screen depends on
- Prefetch the page the user is most likely to open next
- Add a service worker for caching and offline support
- Multiplex over HTTP/2 or HTTP/3

### Rendering Performance

**Do not thrash layout**:
```javascript
// ❌ Interleaved reads and writes force a reflow each pass
rows.forEach(row => {
  const height = row.offsetHeight; // Read (forces layout)
  row.style.height = height * 2; // Write
});

// ✅ Read everything first, then write everything
const heights = rows.map(row => row.offsetHeight); // All reads
rows.forEach((row, i) => {
  row.style.height = heights[i] * 2; // All writes
});
```

**Give the renderer less to do**:
- Mark self-contained regions with the CSS `contain` property
- Keep the DOM shallow — depth costs more than breadth
- Keep the DOM small; every node is work
- Set `content-visibility: auto` on long stretches of content
- Virtualize genuinely long lists with react-window or react-virtualized

**Cut paint and composite cost**:
- Animate through `transform` and `opacity`, which the GPU handles
- Never animate layout properties such as width, height, top, or left
- Apply `will-change` only where you know an expensive operation is coming
- Keep painted regions small; area translates directly into cost

### Animation Performance

**Let the GPU do it**:
```css
/* ✅ Composited on the GPU (fast) */
.panel-slide {
  transform: translateX(100px);
  opacity: 0.5;
}

/* ❌ Forces layout and paint on the CPU (slow) */
.panel-slide {
  left: 100px;
  width: 300px;
}
```

**Hold 60fps**:
- The frame budget is 16ms
- Schedule JavaScript animation through `requestAnimationFrame`
- Throttle or debounce anything bound to scroll
- Prefer CSS animation where CSS can express it
- Keep long-running JavaScript away from an animating frame

**Intersection Observer**:
```javascript
// Cheap way to know when something reaches the viewport
const viewportWatcher = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      // Now visible — trigger the load or the animation
    }
  });
});
```

### Framework-Level Work

**In React**:
- Wrap costly components in `memo()`
- Cache expensive computations with `useMemo()` and `useCallback()`
- Virtualize long lists
- Split code at the route boundary
- Stop creating new functions inline during render
- Profile with the React DevTools Profiler

**Whatever the framework**:
- Cut down on re-renders
- Debounce operations that cost real work
- Memoize derived values
- Load routes and components on demand

### Network

**Fewer round trips**:
- Merge small files together
- Serve icons from an SVG sprite
- Inline small assets the first paint needs
- Remove third-party scripts nobody depends on

**Better API behavior**:
- Paginate instead of returning the whole collection
- Ask GraphQL only for the fields you render
- Compress responses with gzip or brotli
- Set HTTP caching headers deliberately
- Serve static assets from a CDN

**When the connection is bad**:
- Adapt what you load based on `navigator.connection`
- Update the UI optimistically
- Prioritize the requests that matter
- Build up from a working baseline through progressive enhancement

## Hitting the Core Web Vitals Thresholds

### Largest Contentful Paint (LCP < 2.5s)
- Tune whatever the hero element is, usually an image
- Inline the CSS needed to paint it
- Preload the resources it depends on
- Serve through a CDN
- Render on the server

### Interaction to Next Paint (INP: good at or below 200ms at the 75th percentile)
- Slice long tasks into smaller ones
- Defer JavaScript that is not needed immediately
- Move heavy computation into a web worker
- Reduce total JavaScript execution time

### Cumulative Layout Shift (CLS < 0.1)
- Declare dimensions on images and videos
- Never insert content above what is already rendered
- Reserve the box with the `aspect-ratio` CSS property
- Hold space for ads and embeds before they arrive
- Rule out animations that push the layout around

```css
/* Hold the slot before the media loads */
.thumb-frame {
  aspect-ratio: 16 / 9;
}
```

## Instrumentation

**What to measure with**:
- Chrome DevTools — the Lighthouse and Performance panels
- WebPageTest
- Chrome UX Report for Core Web Vitals in the field
- Bundle analyzers such as webpack-bundle-analyzer
- Production monitoring through Sentry, DataDog, or New Relic

**What to watch**:
- The Core Web Vitals trio: LCP, INP, CLS
- Time to Interactive (TTI)
- First Contentful Paint (FCP)
- Total Blocking Time (TBT)
- Total bundle weight
- Number of requests

**IMPORTANT**: run the numbers on real hardware over real networks. A desktop Chrome session on fast fiber tells you nothing about your users.

**Practices to avoid**:
- Changing code before you have measured anything — that is optimization by guesswork
- Trading away accessibility for speed
- Breaking behavior in the name of performance
- Sprinkling `will-change` everywhere, which spawns layers and eats memory
- Lazy loading content that sits above the fold
- Polishing micro-optimizations while the dominant bottleneck goes untouched — always take the biggest one first
- Leaving mobile out of scope, where the devices are slower and so are the networks

## Confirm the Win

Verify that the work paid off:

- **The numbers**: put the before and after Lighthouse scores side by side
- **Real users**: watch field monitoring for the same improvement
- **Range of hardware**: try a low-end Android, not only the newest iPhone
- **Constrained networks**: throttle to 3G and live with the result
- **Nothing broken**: functionality still behaves as it did
- **Felt speed**: does it actually *seem* faster?

Speed is part of the product. A fast interface reads as more responsive, more polished, and more professional than a slow one doing the same job. Work through the bottlenecks in order, keep measuring honestly, and put user-perceived speed at the top of the list.
