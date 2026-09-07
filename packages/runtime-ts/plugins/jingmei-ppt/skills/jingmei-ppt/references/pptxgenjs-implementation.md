# PptxGenJS implementation guidance

Use PptxGenJS as the preferred technical route for a new, editable PowerPoint when JavaScript is available and the deck benefits from reusable layouts, native charts, tables, or deterministic generation. Keep the visual recipe independent of the library so another implementation can reproduce the same design intent.

## Structure the project as a design system

Separate four layers:

1. Content model: claims, evidence, data, sources, and slide roles.
2. Design tokens: palette roles, typography roles, spacing rhythm, line treatment, and semantic status colors.
3. Primitives: text, rules, panels, images, charts, tables, progress indicators, source notes, and folios.
4. Slide compositions: named layout functions that combine primitives for a specific narrative job.

Avoid placing all styling and coordinates directly in slide content code. Let a style recipe change tokens and composition choices without rewriting the content model.

## Translate aesthetic judgment into flexible code

- Express colors by role rather than by slide: `ink`, `muted`, `accent`, `surface`, `positive`, `caution`, `risk`.
- Express typography by role: `deckTitle`, `claim`, `sectionLabel`, `body`, `annotation`, `source`.
- Use a small spacing scale and consistent outer margins, then allow composition-specific exceptions.
- Create helpers for repeated chrome such as title bands, source lines, page numbers, and status markers.
- Create a dedicated single-line primitive for short tokens such as sequence numbers, dates, percentages, amounts, page numbers, weeks, and uppercase codes. Do not treat these as ordinary paragraph text.
- Represent style variants as configuration objects or composition choices, not duplicated deck generators.
- Keep coordinates local to each composition. Avoid one universal layout that forces unrelated content into the same silhouette.

## Preserve PowerPoint quality

- Prefer native PowerPoint text, shapes, charts, and tables for business content that users will edit.
- Use raster or vector images when imagery is the content, while keeping captions and annotations editable.
- Define slide masters or shared chrome when the library and workflow support them cleanly.
- Add source blocks to speaker notes when required by the presentation workflow.
- Use fonts likely to exist in the target environment or provide intentional fallbacks.
- Design for the actual 16:9 canvas and test the smallest meaningful text at rendered size.

## Protect short tokens from wrapping

Short values such as `01`, `25%`, `2026 Q2`, `¥3.2M`, `W1`, and `P0` can wrap into a vertical stack when a text box is narrow. The usual causes are internal text margins, font substitution, slightly different renderer metrics, and PptxGenJS's default `wrap: true`. This is automatic wrapping, not intentional vertical text.

Use a dedicated primitive for these values. It should:

- set `margin: 0` so the token receives the full box width;
- set `wrap: false` and `vert: "horz"` explicitly;
- use `fit: "shrink"` as a compatibility fallback;
- estimate a safe minimum width before adding the text, reduce the requested font size only when necessary, and warn when even the minimum font size will not fit;
- use a stable font with reliable Latin and numeral metrics in the target environment.

`breakLine: false` on a rich-text run only controls an explicit line break; it does not disable automatic wrapping. Likewise, `fit: "shrink"` is a safety net, not permission to create an undersized box. Give the token a sensible width whenever the composition allows it.

Use [pptx-text-guards.mjs](../scripts/pptx-text-guards.mjs):

```js
import { addSingleLineToken } from "./scripts/pptx-text-guards.mjs";

addSingleLineToken(slide, "01", {
  x: 0.9, y: 2.1, w: 0.42, h: 0.42,
  fontFace: "Arial",
  fontSize: 28,
  bold: true,
  color: "287FD1",
  align: "center",
});
```

Route likely tokens through this helper at generation time. A practical first-pass recognizer is `isShortToken`; semantic routing is preferable when the content model already knows that a value is a folio, date, percentage, amount, week, status code, or sequence number. This guard is a cheap structural check and does not require an extra render pass.

## Make image fitting renderer-safe

Treat `sizing: { type: "cover" }` and `sizing: { type: "crop" }` as viewer-dependent OOXML cropping. They write source-rectangle percentages into the presentation while keeping the original bitmap. PowerPoint usually interprets this correctly, but LibreOffice may occasionally render an uncropped image stretched to the target box, especially when a landscape image enters a portrait container.

When LibreOffice, Google Slides import, or cross-renderer consistency matters, bake the crop before adding the image:

1. Read the source bitmap dimensions and orientation.
2. Crop and resize it to the target container's aspect ratio in pixels.
3. Save a project-local derivative with a unique name for that crop.
4. Add the derivative with plain `x`, `y`, `w`, and `h`; omit `sizing`.
5. Render a landscape-to-portrait test in LibreOffice only when the runtime or helper is unverified, the target explicitly includes LibreOffice, or a final render reveals a crop problem. Otherwise rely on the helper's pixel-dimension check and the normal final render.

Use [raster-fit.mjs](../scripts/raster-fit.mjs) when Sharp is available:

```bash
node scripts/raster-fit.mjs source.jpg fitted.png --width 720 --height 1200 --fit cover --position attention
```

Then place it without runtime cropping:

```js
slide.addImage({ path: "fitted.png", x: 8.6, y: 1.4, w: 3.0, h: 5.0 });
```

Generate the derivative near the resolution actually needed. Around 150–220 pixels per PowerPoint inch is usually sufficient for slide imagery; use more for detailed images that may be zoomed. Keep the uncropped source for later layout changes.

Use PptxGenJS `cover` only when the deck is PowerPoint-first, the crop is non-critical, or the same image must remain dynamically reusable. Do not work around the problem by stretching the image or by relying on an oversized image hidden outside the slide.

## Fast default build loop

1. Draft the narrative and compact style brief.
2. Define tokens and compositions, then generate the full deck directly.
3. Run cheap structural checks and render the final deck once.
4. Review a montage for hierarchy, pacing, repetition, and bottom resolution.
5. Inspect the cover, densest slide, unusual media or chart slide, closing slide, and montage anomalies at full size.
6. Revise only affected slides and rerender only what the available workflow can update efficiently; avoid rebuilding validation artifacts that are already current.

## Escalate validation selectively

- Pre-render two or three representative slides only when inventing a new style, building a long deck with repeated layouts, or testing a composition with uncertain fit.
- Inspect every slide at full size when required by the presentation-authoring workflow, when the deck is high-stakes, or when density and visual variation make montage review insufficient.
- Cross-render only for an explicit cross-application requirement or a known risk involving fonts, OOXML cropping, charts, video, SVG, or imported masters.
- Do not repeat a crop A/B test after `raster-fit.mjs` has been validated in the current environment unless the library, renderer, or image pipeline changes.

## Use PptxGenJS selectively

Choose another route when preserving an existing PowerPoint's masters and inherited placeholders is more important than rebuilding; when the output must be native Google Slides; or when browser-native animation and interaction define the experience. The visual system should survive the route change.

## Common engineering symptoms of weak design

- A single global font-size reduction is used to solve every overflow.
- Repeated `addText` and `addShape` calls drift in spacing because no primitives exist.
- Charts are moved independently from their panels or annotations.
- The title and body use unrelated coordinate assumptions, causing a narrow title gap and an empty bottom band.
- Every slide is built from the same card grid even when the narrative job changes.
- Style variants duplicate full source files instead of sharing tokens and composition logic.

Correct these at the design-system layer before polishing individual coordinates.
