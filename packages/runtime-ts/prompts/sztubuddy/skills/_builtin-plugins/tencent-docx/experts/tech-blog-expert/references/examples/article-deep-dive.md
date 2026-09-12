# 原理解析型文章范例

`展示如何用 [概念类比 + 代码验证 + 图表辅助] 解释复杂技术原理`

## 范例：React Server Components 深度解析（仿真节选）

%% 标题策略：技术关键词 + 价值描述
%% "深度解析"锁定中高级读者，"从原理到实践"表明有代码

### 标题
> React Server Components 深度解析：从渲染原理到实践避坑

### TL;DR

%% TL;DR 必须3句话以内说清核心价值
%% 让忙的读者10秒内决定是否继续读

> RSC 让 React 组件可以在服务端运行，直接访问数据库和文件系统，
> 且不会向客户端发送任何 JavaScript。
> 它不是 SSR 的替代品，而是与 SSR 互补的新渲染模式。

### 背景段落

%% 策略：痛点驱动 → 让读者感觉"这跟我有关"
%% 不要上来就讲技术定义，先讲"为什么需要它"

```markdown
## 背景：为什么需要 Server Components？

你可能遇到过这样的场景：

一个简单的博客详情页，你引入了 `marked` 来渲染 Markdown，
引入了 `highlight.js` 来做代码高亮，再加上日期格式化库...
最终这个"简单页面"打包出了 200KB 的 JavaScript。

用户加载了这些 JS，但它们只是把服务端已经有的数据格式化了一下
——这些工作完全可以在服务端做。

这就是 React Server Components 要解决的核心问题：
**让"只负责渲染"的组件在服务端运行，零 JS 发送到客户端。**
```

### 核心概念段落

%% 策略：用类比帮助理解
%% 技术概念首次出现 → 一句话解释 → 类比加深理解

```markdown
## 核心概念：Server vs Client Components

把 React 组件想象成餐厅的工作人员：

| 角色 | 类比 | 特点 |
|------|------|------|
| Server Component | 后厨 | 用户看不到你，但你准备了所有食材 |
| Client Component | 服务员 | 面对用户，处理交互（点菜、催单） |

后厨（Server Component）可以直接进冰箱拿食材（访问数据库），
但不需要出现在用户面前（不发送 JS）。

服务员（Client Component）需要面对用户（`'use client'`），
处理互动（`onClick`、`useState`）。
```

### 代码验证段落

%% 策略：最简示例 → 对比写法 → 关键行注释
%% 代码必须标注版本，关键行必须有注释

```markdown
### 代码对比

**传统 Client Component（以前的写法）**：

\`\`\`tsx
// app/blog/[id]/page.tsx (Client Component)
'use client'; // 👈 声明为客户端组件

import { marked } from 'marked';      // ⚠️ 这个库会打包到客户端
import hljs from 'highlight.js';       // ⚠️ 又多了 50KB

export default function BlogPost({ id }: { id: string }) {
  const [post, setPost] = useState(null);

  useEffect(() => {
    fetch(\`/api/posts/\${id}\`).then(r => r.json()).then(setPost);
  }, [id]);

  if (!post) return <Loading />;
  return <div dangerouslySetInnerHTML={{ __html: marked(post.content) }} />;
}
// 📊 打包体积：~200KB JS 发送到客户端
\`\`\`

**Server Component（新写法）**：

\`\`\`tsx
// app/blog/[id]/page.tsx (Server Component, 默认就是)
// 注意：没有 'use client'，默认就是 Server Component

import { marked } from 'marked';      // ✅ 只在服务端运行，不打包到客户端
import hljs from 'highlight.js';       // ✅ 同上
import { db } from '@/lib/db';         // ✅ 可以直接访问数据库！

export default async function BlogPost({ params }: { params: { id: string } }) {
  const post = await db.posts.findById(params.id);  // 👈 直接查数据库
  const html = marked(post.content, { highlight: code => hljs.highlight(code).value });

  return <article dangerouslySetInnerHTML={{ __html: html }} />;
}
// 📊 打包体积：0KB JS 发送到客户端 🎉
\`\`\`
```

### 反模式对照

```
❌ "React Server Components 是 React 团队提出的一种新的组件类型，
    它允许组件在服务端渲染..."
   → 文档翻译体，直接抄 RFC 定义

❌ 不标注版本：React 几？Next.js 几？
   → 版本盲，读者可能用的是 React 17

✅ "把 React 组件想象成餐厅的工作人员..."
   → 类比+表格，降低认知负荷

✅ 代码对比 + 体积数据
   → Show, Don't Tell
```
