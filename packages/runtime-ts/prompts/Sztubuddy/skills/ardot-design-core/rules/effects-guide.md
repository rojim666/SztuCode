# Effects Guide — Composite Visual Effects

> For basic capabilities (Effects/Fills/BlendMode types, parameter formats, multi-layer stacking, text-node shadow specifics), see general-design-information.md.

## Composite Effect Recipes

### Glassmorphism
> **Trigger keywords**: glass, backdrop-blur, translucent-surface, frosted, 毛玻璃

BACKGROUND_BLUR + semi-transparent SOLID fill (opacity must be below 0.5) + INNER_SHADOW edge highlight + DROP_SHADOW for elevation + white 1px stroke at 15-30% opacity.

```javascript
effects: [
  {type: "BACKGROUND_BLUR", blurType: "NORMAL", radius: 16, visible: true, boundVariables: {}},
  {type: "DROP_SHADOW", color: {r:0, g:0, b:0, a:0.15}, offset: {x:0, y:8}, radius: 24, visible: true, blendMode: "NORMAL", showShadowBehindNode: false, boundVariables: {}},
  {type: "INNER_SHADOW", color: {r:1, g:1, b:1, a:0.2}, offset: {x:0, y:1}, radius: 2, visible: true, blendMode: "NORMAL", boundVariables: {}}
]
fills: [{type: "SOLID", color: {r:1, g:1, b:1}, opacity: 0.2, visible: true, blendMode: "NORMAL"}]
strokes: [{type: "SOLID", color: {r:1, g:1, b:1}, opacity: 0.25, visible: true, blendMode: "NORMAL"}]
strokeWeight: 1
```

> **showShadowBehindNode rule**: Set to `false` when the node has a semi-transparent fill (opacity < 1) — otherwise the shadow bleeds through the transparent area. Set to `true` when the node is fully opaque — otherwise the outer shadow won't render.

### Neon Glow
> **Trigger keywords**: neon, neon-text-shadow, ambient-glow, accent-glow, 霓虹, 发光文字

Apply 4-6 layers of DROP_SHADOW directly on the text node, with radius decreasing and opacity increasing from outer to inner. Shadows must be on the text node itself to follow the glyph outline.

```javascript
// 示例：蓝色霓虹（根据实际品牌色调整 r/g/b）
effects: [
  {type: "DROP_SHADOW", color: {r:0.2, g:0.4, b:1, a:0.10}, offset: {x:0, y:0}, radius: 80, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}},
  {type: "DROP_SHADOW", color: {r:0.2, g:0.4, b:1, a:0.25}, offset: {x:0, y:0}, radius: 40, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}},
  {type: "DROP_SHADOW", color: {r:0.2, g:0.4, b:1, a:0.50}, offset: {x:0, y:0}, radius: 20, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}},
  {type: "DROP_SHADOW", color: {r:0.2, g:0.4, b:1, a:0.80}, offset: {x:0, y:0}, radius: 10, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}},
  {type: "DROP_SHADOW", color: {r:0.2, g:0.4, b:1, a:1.00}, offset: {x:0, y:0}, radius: 4, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}}
]
```

### Metallic
> **Trigger keywords**: metallic, metal, chrome, multi-stop-gradient, 金属, 铬

GRADIENT_LINEAR with 5 color stops alternating dark/light (dark→bright→dark→bright→dark), angled at 45°. The metallic feel comes from the contrast ratio and alternation frequency between stops.

```javascript
// 银色金属
fills: [{type: "GRADIENT_LINEAR",
  gradientStops: [
    {color: {r:0.745, g:0.765, b:0.788, a:1}, position: 0},
    {color: {r:0.941, g:0.941, b:0.941, a:1}, position: 0.25},
    {color: {r:0.557, g:0.573, b:0.596, a:1}, position: 0.50},
    {color: {r:0.910, g:0.910, b:0.910, a:1}, position: 0.75},
    {color: {r:0.424, g:0.439, b:0.471, a:1}, position: 1}
  ],
  gradientTransform: [[0.707, 0.707, 0], [-0.707, 0.707, 0]],
  opacity: 1, visible: true, blendMode: "NORMAL"}]
effects: [
  {type: "INNER_SHADOW", color: {r:0, g:0, b:0, a:0.3}, offset: {x:0, y:2}, radius: 4, visible: true, blendMode: "NORMAL", boundVariables: {}},
  {type: "INNER_SHADOW", color: {r:1, g:1, b:1, a:0.2}, offset: {x:0, y:-1}, radius: 2, visible: true, blendMode: "NORMAL", boundVariables: {}}
]
```

### Glow Border
> **Trigger keywords**: glow-border, ambient-glow, inner-glow, accent-tinted, 内发光, 发光边框

INNER_SHADOW ×2 (zero-offset, brand color, radius 2-6) + outer DROP_SHADOW for ambient glow. Works best on smaller elements.

```javascript
// 示例：蓝色发光边框
effects: [
  {type: "INNER_SHADOW", color: {r:0.2, g:0.4, b:1, a:0.8}, offset: {x:0, y:0}, radius: 4, visible: true, blendMode: "NORMAL", boundVariables: {}},
  {type: "INNER_SHADOW", color: {r:0.2, g:0.4, b:1, a:0.4}, offset: {x:0, y:0}, radius: 8, visible: true, blendMode: "NORMAL", boundVariables: {}},
  {type: "DROP_SHADOW", color: {r:0.2, g:0.4, b:1, a:0.2}, offset: {x:0, y:0}, radius: 16, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}}
]
```

### Iridescent Gradient
> **Trigger keywords**: iridescent, iridescent-gradient, holographic, oil-slick, 虹彩, 全息

GRADIENT_ANGULAR with 6-8 hue-evenly-distributed stops + GRADIENT_RADIAL in SCREEN blendMode to brighten the center. Base color must not be too dark.

```javascript
fills: [
  {type: "GRADIENT_ANGULAR",
    gradientStops: [
      {color: {r:1, g:0.2, b:0.4, a:1}, position: 0},
      {color: {r:1, g:0.6, b:0.2, a:1}, position: 0.17},
      {color: {r:0.8, g:1, b:0.2, a:1}, position: 0.33},
      {color: {r:0.2, g:1, b:0.6, a:1}, position: 0.50},
      {color: {r:0.2, g:0.6, b:1, a:1}, position: 0.67},
      {color: {r:0.6, g:0.2, b:1, a:1}, position: 0.83},
      {color: {r:1, g:0.2, b:0.4, a:1}, position: 1}
    ],
    gradientTransform: [[1, 0, 0], [0, 1, 0]],
    opacity: 1, visible: true, blendMode: "NORMAL"},
  {type: "GRADIENT_RADIAL",
    gradientStops: [
      {color: {r:1, g:1, b:1, a:0.4}, position: 0},
      {color: {r:1, g:1, b:1, a:0}, position: 1}
    ],
    gradientTransform: [[1, 0, 0], [0, 1, 0]],
    opacity: 1, visible: true, blendMode: "SCREEN"}
]
```

### Neumorphism
> **Trigger keywords**: neumorphism, neumorphic, soft-ui, dual-shadow, convex, concave, 新拟态

Same-color raised/recessed appearance. Background and element color must match (e.g. #E0E5EC). Background cannot be pure white or pure black.

```javascript
// 凸起
effects: [
  {type: "DROP_SHADOW", color: {r:1, g:1, b:1, a:0.8}, offset: {x:-6, y:-6}, radius: 8, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}},
  {type: "DROP_SHADOW", color: {r:0.639, g:0.690, b:0.780, a:0.5}, offset: {x:6, y:6}, radius: 8, visible: true, blendMode: "NORMAL", showShadowBehindNode: true, boundVariables: {}}
]

// 凹陷
effects: [
  {type: "INNER_SHADOW", color: {r:0.639, g:0.690, b:0.780, a:0.5}, offset: {x:4, y:4}, radius: 8, visible: true, blendMode: "NORMAL", boundVariables: {}},
  {type: "INNER_SHADOW", color: {r:1, g:1, b:1, a:0.8}, offset: {x:-4, y:-4}, radius: 8, visible: true, blendMode: "NORMAL", boundVariables: {}}
]
```

## Unsupported Effects

| Effect | Reason | Workaround |
|--------|--------|-----------|
| Noise texture | NOISE kernel not implemented | IMAGE fill + OVERLAY BlendMode |
| Liquid glass | GLASS kernel not implemented | BACKGROUND_BLUR + gradient + INNER_SHADOW approximation |
| Texture overlay | TEXTURE kernel not implemented | IMAGE fill + BlendMode |
| Clip path / irregular shape | No CLIP_PATH support | Not supported |
