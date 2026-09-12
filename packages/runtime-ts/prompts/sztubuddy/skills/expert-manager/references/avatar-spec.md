# 头像生成规范

## 基本要求

| 项目 | 要求 |
|------|------|
| 格式 | PNG（推荐）或 JPG |
| 尺寸 | 512×512 px（正方形） |
| 大小 | 单张不超过 500KB |
| 风格 | 统一漫画/插画风格，专业自然 |
| 内容 | 符合角色定位，不含违规内容 |

> 使用 `ImageGen` 工具生成，`size` 参数设为 `"1024x1024"`（高清大图，市场缩放为 512×512 展示）。

## 生成策略

**Agent 型**：1 张头像
- `avatars/expert.png`

**Team 型**：N+1 张头像
- `avatars/team.png` — 团队整体头像
- `avatars/{team}-team-lead.png` — 主理人头像
- `avatars/{member-name}.png` — 每个团员头像

---

## Prompt 构建核心原则

**每个头像的 prompt 必须从对应的 MD 文件描述中提取角色特征，不使用通用模板硬编码。**

### 提取步骤

1. **读取 Agent MD 文件**
2. **提取角色身份**：从标题和首段提取
3. **提取专业特征**：从"核心能力"章节提取关键词，转化为视觉元素
4. **推断工作风格**：从"工作流程"和"注意事项"推断性格气质
5. **推断人物属性**：从 name 字段推断性别和风格基调

---

## 个人头像 Prompt 组装

```
[风格前缀] + [角色身份] + [外观特征] + [表情气质] + [背景元素] + [质量后缀]
```

| 部分 | 说明 | 示例 |
|------|------|------|
| 风格前缀 | 统一漫画/插画风格 | `Professional cartoon-style illustration avatar,` |
| 角色身份 | 从 MD 标题/首段提取 | `a female design system document architect` |
| 外观特征 | 从核心能力推断穿着/配饰 | `wearing stylish glasses, holding a design specification document` |
| 表情气质 | 从工作风格推断 | `confident and meticulous expression` |
| 背景元素 | 从专业领域提取视觉符号 | `subtle design tokens and color palette swatches in background` |
| 质量后缀 | 固定 | `Bust shot, facing forward. Clean simple background. High quality, professional, natural.` |

### 示例 1：设计系统架构师

MD 核心内容：角色=设计系统文档架构师，能力=9大标准章节、AI可读格式，输出=Markdown+HEX+CSS

```
Professional cartoon-style illustration avatar, a female design system document architect,
wearing stylish glasses, holding a design guideline document, modern creative smart casual attire,
confident and meticulous expression with a creative yet precise aura,
subtle color palette swatches, typography samples and design token symbols in the background.
Bust shot, facing forward. Clean simple warm-toned background. High quality, professional, natural.
```

### 示例 2：技术分析师

MD 核心内容：角色=技术分析师，能力=K线形态、均线分析、MACD/RSI/KDJ

```
Professional cartoon-style illustration avatar, a male technical stock market analyst named Marco,
wearing a sharp vest over dress shirt, looking at holographic candlestick charts,
focused and analytical expression with sharp observant eyes,
K-line charts, moving average lines and MACD indicators floating in the background.
Bust shot, facing forward. Clean simple blue-toned background. High quality, professional, natural.
```

---

## 团队头像 Prompt 构建

**输入来源**：plugin.json 的 `displayDescription` + 主理人 MD 的团队描述

### 提取步骤

1. **团队定位**：从 displayDescription 提取团队做什么
2. **协作模式**：从主理人 MD 的 SOP 提取工作阶段
3. **成员构成**：从成员列表提取角色类型的多样性
4. **视觉表达**：将以上信息转化为体现团队协作的场景

### Prompt 组装

```
[风格前缀] + [团队场景描述] + [协作元素] + [成员象征] + [质量后缀]
```

### 示例：交易分析团队

```
Professional cartoon-style illustration, a dynamic stock trading analysis team scene,
multiple diverse analysts gathered around a central holographic display showing candlestick charts,
a bull figure and a bear figure debating on opposite sides symbolizing bull-bear debate,
risk gauges and decision dashboards floating around,
warm collaborative atmosphere with focused professional energy.
Clean simple multi-tone gradient background. High quality, professional, team composition.
```

---

## 同一团队风格统一规则

Team 型的所有头像必须在 prompt 中保持一致的**风格锚定词**：

**固定风格前缀（每个 prompt 开头）：**
```
Professional cartoon-style illustration avatar, consistent art style with warm lighting and soft shadows,
```

**固定质量后缀（每个 prompt 结尾）：**
```
Bust shot, facing forward. Clean simple {color}-toned background. High quality, professional, natural.
```

### 背景色调映射

| categoryId | 背景色调 |
|------------|---------|
| 01-ProductDesign | warm orange-coral |
| 02-Engineering | blue-purple |
| 03-GameSpatial | purple-red gradient |
| 04-DataAI | cyan-teal |
| 05-MarketingGrowth | red-orange |
| 06-ContentCreative | pink-magenta |
| 07-SalesCommerce | golden-amber |
| 08-FinanceInvestment | dark blue with gold accent |
| 09-OperationsHR | navy slate-blue |
| 10-ProjectQuality | green-emerald |
| 11-SecurityCompliance | dark grey-blue |
| 12-IndustryConsultant | deep teal with silver accent |

---

## 执行流程

1. **读取 Agent MD** — 逐个读取 agents/ 下每个 MD
2. **提取角色特征** — 从角色定义、核心能力、工作流程中提取
3. **构建个人 prompt** — 按上述步骤将特征转化为视觉描述
4. **构建团队 prompt**（Team 型）— 从 displayDescription 和主理人 MD 提取
5. **统一风格锚定** — 确保所有 prompt 使用相同的风格前缀和后缀
6. **调用 ImageGen** — 逐张生成，`output_dir` 为专家包的 `avatars/`，`size` 为 `"1024x1024"`
7. **重命名文件** — 将生成的图片重命名为 plugin.json 中声明的文件名
8. **验证** — 确认所有头像文件已存在于 avatars/

## 注意事项

1. **必须基于 MD 描述生成**：不要使用通用 prompt
2. **团队头像体现协作**：不是简单人物剪影
3. **同一团队画风一致**：共用风格锚定词和背景色调
4. **生成失败处理**：在 README.md 中标注需手动补充的头像，附推荐 prompt
5. **用户可替换**：提醒自动生成的头像可手动替换（512×512，PNG/JPG，≤500KB）
