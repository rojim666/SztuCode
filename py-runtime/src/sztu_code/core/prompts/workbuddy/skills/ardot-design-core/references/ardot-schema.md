# Node Property Schema

> 本文档描述设计文件中各节点类型支持的属性，基于 Mixin 组合模式构建。

## Node Types

`DOCUMENT` | `PAGE` | `FRAME` | `GROUP` | `COMPONENT_SET` | `COMPONENT` | `INSTANCE` | `SECTION` | `TEXT` | `VECTOR` | `RECTANGLE` | `ELLIPSE` | `LINE` | `STAR` | `BOOLEAN_OPERATION`

## Property Mixins

### Base (所有节点)
| 属性 | 说明 |
|------|------|
| `id` | 节点唯一标识 |
| `parent` | 父节点引用 |
| `name` | 节点名称 |
| `type` | 节点类型 |
| `removed` | 是否已删除 |
| `isAsset` | 是否为资产 |

### Scene (可见场景节点，除 DOCUMENT/PAGE 外)
| 属性 | 说明 | 默认值 |
|------|------|--------|
| `visible` | 是否可见 | `true` |
| `locked` | 是否锁定 | `false` |
| `stuckNodes` | 吸附节点 | |
| `attachedConnectors` | 附着连接线 | |
| `componentPropertyReferences` | 组件属性引用 | |
| `boundVariables` | 绑定的变量 | |
| `inferredVariables` | 推断的变量 | |
| `resolvedVariableModes` | 解析后的变量模式 | |

### Dimension & Position (位置尺寸)
| 属性 | 说明 |
|------|------|
| `x`, `y` | 坐标位置 |
| `width`, `height` | 尺寸大小 |
| `minWidth`, `maxWidth` | 宽度约束 |
| `minHeight`, `maxHeight` | 高度约束 |
| `absoluteBoundingBox` | 绝对包围盒 |

### Layout (布局)
| 属性 | 说明 | 默认值 |
|------|------|--------|
| `rotation` | 旋转角度 | `0` |
| `layoutSizingHorizontal` | 水平尺寸模式: `FIXED` / `HUG` / `FILL` | `FIXED` |
| `layoutSizingVertical` | 垂直尺寸模式: `FIXED` / `HUG` / `FILL` | `FIXED` |

### Auto Layout Children (自动布局子项)
| 属性 | 说明 | 默认值 |
|------|------|--------|
| `layoutAlign` | 子项对齐方式 | |
| `layoutGrow` | 子项伸展权重 | |
| `layoutPositioning` | 定位方式: `AUTO` / `ABSOLUTE` | `AUTO` |

### Auto Layout (自动布局，Frame 类节点)
| 属性 | 说明 |
|------|------|
| `layoutMode` | 布局方向: `NONE` / `HORIZONTAL` / `VERTICAL` |
| `primaryAxisAlignItems` | 主轴对齐: `MIN` / `CENTER` / `MAX` / `SPACE_BETWEEN` |
| `counterAxisAlignItems` | 交叉轴对齐: `MIN` / `CENTER` / `MAX` / `BASELINE` |
| `counterAxisAlignContent` | 交叉轴内容对齐（换行时） |
| `primaryAxisSizingMode` | 主轴尺寸模式 |
| `counterAxisSizingMode` | 交叉轴尺寸模式 |
| `itemSpacing` | 子项间距 |
| `counterAxisSpacing` | 交叉轴间距（换行时） |
| `paddingTop/Right/Bottom/Left` | 内边距 |
| `layoutWrap` | 是否换行: `NO_WRAP` / `WRAP` |
| `strokesIncludedInLayout` | 描边是否参与布局计算 |
| `itemReverseZIndex` | 子项 Z 轴反转 |

### Blend (混合)
| 属性 | 说明 | 默认值 |
|------|------|--------|
| `opacity` | 不透明度 (0-1) | `1` |
| `blendMode` | 混合模式 | `NORMAL` |
| `isMask` | 是否为蒙版 | |
| `maskType` | 蒙版类型 | |
| `effects` | 效果列表（阴影、模糊等） | |
| `effectStyleId` | 效果样式 ID | |

### Geometry (几何/填充/描边)
| 属性 | 说明 | 默认值 |
|------|------|--------|
| `fills` | 填充列表 | |
| `fillStyleId` | 填充样式 ID | |
| `strokes` | 描边列表 | |
| `strokeStyleId` | 描边样式 ID | |
| `strokeWeight` | 描边粗细 | `1` |
| `strokeAlign` | 描边对齐: `INSIDE` / `OUTSIDE` / `CENTER` | `INSIDE` |
| `strokeJoin` | 描边连接方式 | |
| `strokeCap` | 描边端点样式 | |
| `strokeMiterLimit` | 斜接限制 | |
| `dashPattern` | 虚线模式 | |
| `strokeGeometry` | 描边几何数据 | |
| `fillGeometry` | 填充几何数据 | |

### Individual Strokes (独立描边，Frame 类)
`strokeTopWeight` / `strokeBottomWeight` / `strokeLeftWeight` / `strokeRightWeight`

### Corner (圆角)
| 属性 | 说明 |
|------|------|
| `cornerRadius` | 统一圆角 |
| `cornerSmoothing` | 圆角平滑度 |
| `topLeftRadius` / `topRightRadius` / `bottomLeftRadius` / `bottomRightRadius` | 独立圆角 |

### Constraint (约束)
`constraints` — 相对父节点的约束规则

### Text (文本专有)
| 属性 | 说明 |
|------|------|
| `characters` | 文本内容 |
| `fontSize` | 字号 |
| `fontName` | 字体名 |
| `fontWeight` | 字重 |
| `lineHeight` | 行高 |
| `letterSpacing` | 字间距 |
| `textAlignHorizontal` | 水平对齐 |
| `textAlignVertical` | 垂直对齐 |
| `textAutoResize` | 自动调整模式 |
| `textTruncation` | 截断模式 |
| `maxLines` | 最大行数 |
| `textCase` | 大小写转换 |
| `textDecoration` | 文字装饰 |
| `textStyleId` | 文字样式 ID |
| `hyperlink` | 超链接 |
| `paragraphIndent` / `paragraphSpacing` | 段落缩进/间距 |
| `leadingTrim` | 行距修剪 |
| `hasMissingFont` | 是否缺失字体 |
| `autoRename` | 自动重命名 |

### Component (组件专有)
| 属性 | 说明 |
|------|------|
| `componentPropertyDefinitions` | 组件属性定义 |
| `variantProperties` | 变体属性 |
| `description` / `descriptionMarkdown` | 组件描述 |
| `documentationLinks` | 文档链接 |
| `remote` | 是否远程组件 |
| `key` | 组件唯一 Key |

### Instance (实例专有)
| 属性 | 说明 |
|------|------|
| `mainComponent` | 主组件引用 |
| `componentProperties` | 组件属性值 |
| `scaleFactor` | 缩放因子 |
| `exposedInstances` | 暴露的实例 |
| `isExposedInstance` | 是否被暴露 |
| `overrides` | 覆盖列表 |

### Other
| 属性 | 说明 |
|------|------|
| `children` | 子节点列表 |
| `expanded` | 是否展开（容器） |
| `clipsContent` | 是否裁切溢出内容（默认 `false`） |
| `targetAspectRatio` | 锁定宽高比 |
| `exportSettings` | 导出配置 |
| `reactions` | 交互动作 |
| `devStatus` | 开发状态 |
| `detachedInfo` | 解除关联信息 |
| `layoutGrids` / `gridStyleId` | 布局网格 |
| `guides` | 参考线 |
| `backgrounds` / `backgroundStyleId` | 背景（已废弃） |
| `arcData` | 弧形数据（Ellipse） |
| `pointCount` | 顶点数（Star/Polygon） |
| `innerRadius` | 内半径（Star） |
| `booleanOperation` | 布尔运算类型 |
| `sectionContentsHidden` | Section 内容隐藏 |
| `selection` | 当前选中（Page） |

### 3D Transform
`transformIndependent` / `transform3DPosture` / `transform3DDepth` / `transform3DOrigin` / `transform3DHideBackface` / `transform3DPerspective`

---

## Node → Mixin 组合关系

| Node Type | Mixin 组合 |
|-----------|-----------|
| **DOCUMENT** | Base |
| **PAGE** | Base + Export + `guides`, `selection` |
| **FRAME** | Base + Scene + Children + Container + Background + Geometry + Corner + RectCorner + Blend + Constraint + Layout + Export + IndividualStrokes + AutoLayout + AspectRatio + DevStatus + Reaction + `clipsContent`, `layoutGrids`, `guides`, `detachedInfo` |
| **GROUP** | Base + Scene + Reaction + Children + Container + Background + Blend + Layout + Export + AspectRatio |
| **RECTANGLE** | DefaultShape + Constraint + Corner + RectCorner + IndividualStrokes + AspectRatio |
| **ELLIPSE** | DefaultShape + Constraint + Corner + AspectRatio + `arcData` |
| **LINE** | DefaultShape + Constraint |
| **STAR** | DefaultShape + Constraint + Corner + AspectRatio + `pointCount`, `innerRadius` |
| **VECTOR** | DefaultShape + Constraint + Corner + AspectRatio |
| **TEXT** | DefaultShape + Constraint + Text + AspectRatio |
| **COMPONENT_SET** | BaseFrame + Publishable + ComponentProperty + `defaultVariant`, `variantGroupProperties` |
| **COMPONENT** | DefaultFrame + Publishable + Variant + ComponentProperty |
| **INSTANCE** | DefaultFrame + Variant + `mainComponent`, `scaleFactor`, `componentProperties`, `exposedInstances`, `isExposedInstance`, `overrides` |
| **BOOLEAN_OPERATION** | DefaultShape + Children + Corner + Container + AspectRatio + `booleanOperation` |
| **SECTION** | Children + MinimalFills + Opaque + DevStatus + AspectRatio + `sectionContentsHidden` |

> **DefaultShape** = Base + Scene + Reaction + Blend + Geometry + Layout + Export
> **BaseFrame** = Base + Scene + Children + Container + Background + Geometry + Corner + RectCorner + Blend + Constraint + Layout + Export + IndividualStrokes + AutoLayout + AspectRatio + DevStatus + extras
> **DefaultFrame** = BaseFrame + Reaction

## 属性默认值（省略优化）

序列化时，值等于默认值的属性会被省略：

```
visible: true, rotation: 0, opacity: 1, clipsContent: false,
locked: false, layoutPositioning: "AUTO", blendMode: "NORMAL",
strokeAlign: "INSIDE", strokeWeight: 1,
layoutSizingHorizontal: "FIXED", layoutSizingVertical: "FIXED"
```
