const DEFAULT_EM_FACTOR = 0.62;

export function estimateSingleLineWidth(value, fontSize, {
  emFactor = DEFAULT_EM_FACTOR,
  paddingIn = 0.14,
  safety = 1.15,
} = {}) {
  const text = String(value ?? "").trim();
  const size = Number(fontSize);
  if (!Number.isFinite(size) || size <= 0) {
    throw new TypeError("fontSize must be a positive number");
  }
  return (text.length * size * emFactor / 72 + paddingIn) * safety;
}

export function isShortToken(value) {
  const text = String(value ?? "").trim();
  if (!text || text.length > 16 || /\s{2,}|[\r\n]/u.test(text)) return false;

  return (
    /^\d{1,4}$/u.test(text) ||
    /^\d+(?:[.,]\d+)?%$/u.test(text) ||
    /^[¥$€£]\s?\d+(?:[.,]\d+)?(?:[KMB万亿])?$/iu.test(text) ||
    /^\d{4}(?:[-/.]\d{1,2}){0,2}$/u.test(text) ||
    /^\d{4}\s?Q[1-4]$/iu.test(text) ||
    /^(?:W|P|Q|H)\d{1,3}$/iu.test(text) ||
    /^[A-Z0-9][A-Z0-9+%./:–—-]{0,11}$/u.test(text)
  );
}

export function addSingleLineToken(slide, value, options = {}) {
  if (!slide || typeof slide.addText !== "function") {
    throw new TypeError("slide must provide an addText method");
  }

  const {
    minFontSize = 12,
    warn = console.warn,
    autoShrink = true,
    widthEstimate = {},
    ...textOptions
  } = options;

  const requestedFontSize = Number(textOptions.fontSize ?? 18);
  const boxWidth = Number(textOptions.w);
  if (!Number.isFinite(boxWidth) || boxWidth <= 0) {
    throw new TypeError("addSingleLineToken requires a positive w value");
  }
  if (!Number.isFinite(requestedFontSize) || requestedFontSize <= 0) {
    throw new TypeError("fontSize must be a positive number");
  }

  const safeMinFontSize = Math.min(requestedFontSize, Math.max(1, Number(minFontSize) || 12));
  const recommendedWidth = estimateSingleLineWidth(value, requestedFontSize, widthEstimate);
  let effectiveFontSize = requestedFontSize;

  if (autoShrink && boxWidth < recommendedWidth) {
    effectiveFontSize = Math.max(
      safeMinFontSize,
      requestedFontSize * boxWidth / recommendedWidth,
    );
  }

  const minimumWidth = estimateSingleLineWidth(value, effectiveFontSize, widthEstimate);
  if (boxWidth < minimumWidth && typeof warn === "function") {
    warn(
      `[pptx-text-guard] "${String(value)}" may still be too narrow: ` +
      `w=${boxWidth.toFixed(2)}in, recommended=${minimumWidth.toFixed(2)}in ` +
      `at ${effectiveFontSize.toFixed(1)}pt`,
    );
  }

  slide.addText(String(value ?? ""), {
    ...textOptions,
    fontSize: effectiveFontSize,
    valign: textOptions.valign ?? "middle",
    margin: 0,
    wrap: false,
    fit: "shrink",
    vert: "horz",
  });

  return {
    adjusted: effectiveFontSize < requestedFontSize,
    requestedFontSize,
    fontSize: effectiveFontSize,
    recommendedWidth,
    boxWidth,
  };
}
