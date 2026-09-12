# 实战经验型文章范例

`展示如何用 [问题→排查→根因→方案→数据] 结构写实战经验文章`

## 范例：Node.js 内存泄漏排查实战（仿真节选）

%% 标题策略：[动作] + [指标从X到Y] → 量化结果吸引点击
%% "实战"表明有真实经验而非理论分析

### 标题
> Node.js 内存泄漏排查：如何将 RSS 从 2GB 降到 200MB

### TL;DR

%% 3句话：问题 → 根因 → 方案

> 生产环境 Node.js 服务 RSS 持续增长到 2GB 后 OOM。
> 根因是 EventEmitter 监听器泄漏——每次请求注册监听但未移除。
> 修复后 RSS 稳定在 200MB，P99 延迟从 800ms 降到 120ms。

### 问题发现段落

%% 策略：用真实数据（即使是仿真的）让文章有说服力
%% 不说"服务变慢了"，说"P99 从 120ms 涨到 800ms"

```markdown
## 问题发现

上线3天后，监控告警：

| 指标 | 正常值 | 异常值 |
|------|--------|--------|
| RSS 内存 | 150-200MB | 2.1GB ↑ |
| P99 延迟 | 120ms | 800ms ↑ |
| GC 频率 | 3次/分钟 | 47次/分钟 ↑ |
| OOM 重启 | 0次/天 | 3-5次/天 |

症状：RSS 持续线性增长，不随请求量下降而释放。
```

### 排查过程段落

%% 策略：展示真实的排查思路，包括走过的弯路
%% 读者最大的收获是"方法论"，不是"答案"

```markdown
## 排查过程

### 尝试 1：heapdump 对比（❌ 未找到根因）

\`\`\`bash
# 间隔5分钟抓两次堆快照
kill -USR2 <pid>  # 第一次
sleep 300
kill -USR2 <pid>  # 第二次
\`\`\`

用 Chrome DevTools 对比两次快照，发现 Object 数量增长了 50K，
但没有明显的大对象泄漏。**弯路：只关注了堆内存，忽略了 EventEmitter。**

### 尝试 2：EventEmitter 监听器计数（✅ 定位根因）

\`\`\`javascript
// 添加临时诊断代码
const emitter = require('events');
const original = emitter.prototype.on;
emitter.prototype.on = function(event, listener) {
  if (this.listenerCount(event) > 10) {
    console.warn(\`⚠️ \${event} has \${this.listenerCount(event)} listeners\`);
    console.trace();  // 👈 打印调用栈，找到注册位置
  }
  return original.call(this, event, listener);
};
\`\`\`

日志中大量输出：
\`\`\`
⚠️ response has 847 listeners
    at RequestHandler.handleRequest (src/handler.ts:42)
\`\`\`

**根因确认**：`handleRequest` 中每次请求都 `on('response', ...)` 
但请求结束后未调用 `removeListener`。
```

### 修复段落

%% 策略：代码 diff + 前后数据对比
%% 让修复方案可复制、可验证

```markdown
## 修复方案

\`\`\`diff
// src/handler.ts
- emitter.on('response', this.onResponse);
+ emitter.once('response', this.onResponse);  // once 自动移除
\`\`\`

或者手动移除：
\`\`\`typescript
const handler = (data: Response) => { /* ... */ };
emitter.on('response', handler);

// 请求结束时清理 👇
req.on('close', () => {
  emitter.removeListener('response', handler);
});
\`\`\`
```

### 效果验证段落

%% 必须有前后对比数据——这是文章最有说服力的部分

```markdown
## 效果验证（修复前 vs 修复后）

| 指标 | 修复前 | 修复后 | 变化 |
|------|--------|--------|------|
| RSS 内存 | 2.1GB | 180MB | **-91%** |
| P99 延迟 | 800ms | 120ms | **-85%** |
| GC 频率 | 47次/min | 3次/min | **-94%** |
| OOM 重启 | 3-5次/天 | 0次/天 | **消除** |
```

### 反模式对照

```
❌ "遇到了内存泄漏问题，排查了很久终于找到了"
   → 缺少数据、缺少过程、缺少方法论

❌ 只给最终答案："用 once 替代 on"
   → 读者不知道为什么，遇到其他泄漏场景无法举一反三

✅ 展示完整排查路径，包括走过的弯路
   → 方法论比答案更有价值
```
