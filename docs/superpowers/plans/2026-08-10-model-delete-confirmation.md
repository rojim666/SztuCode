# 模型删除确认与失败状态实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为桌面端模型删除增加确认、单项忙碌状态和可重试的失败反馈，完整满足 Issue #30。

**Architecture:** 在 `ModelManager.vue` 内使用待确认目标和正在删除 ID 两个局部状态驱动确认对话框与行级按钮状态。确认操作调用现有 `deleteModelProfile`，成功使用返回列表刷新，失败保留列表并显示错误，不引入新协议或全局状态。

**Tech Stack:** Vue 3 `<script setup>`, TypeScript, Lucide Vue, Playwright, Vite。

---

### Task 1: 建立删除交互的失败测试

**Files:**
- Add: `desktop/tests/visual/model-manager.spec.ts`
- Add: `desktop/tests/visual/fixtures/model-manager.html`
- Add: `desktop/tests/visual/fixtures/model-manager.ts`
- Inspect: `desktop/src/components/ModelConfig/ModelManager.vue`

- [x] **Step 1: 准备可控的模型列表与删除服务响应**

在已有模型管理测试的初始化方式上，注入一个当前模型、一个内置模型和一个可删除自定义模型，并让 `deleteModelProfile` 的测试桥接可以分别返回成功或抛出错误。测试不得访问真实网络或持久化用户数据。

- [x] **Step 2: 添加取消路径测试**

点击自定义模型的删除按钮，断言包含模型名称的确认对话框出现；点击取消后断言对话框关闭、删除服务调用次数为 0 且模型仍显示。

- [x] **Step 3: 添加成功路径测试**

点击删除并确认，断言服务只调用一次且传入目标模型 ID；确认期间删除按钮和确认按钮不可重复触发；服务成功返回后对话框关闭、模型从列表移除且错误提示不存在。

- [x] **Step 4: 添加失败与重试路径测试**

让第一次删除抛出可读错误，断言确认框关闭、模型仍显示、管理页显示错误文本；再次点击删除并确认时服务被调用第二次，成功响应后列表更新且错误被清除。

- [x] **Step 5: 运行新增测试确认 RED**

运行 `cd desktop && npx playwright test tests/visual/model-manager.spec.ts`。在生产代码尚未修改时，测试应因确认对话框和错误状态不存在而失败；若立即通过，修正测试使其真正覆盖缺失行为。

### Task 2: 实现确认与删除状态

**Files:**
- Modify: `desktop/src/components/ModelConfig/ModelManager.vue`

- [x] **Step 1: 增加待确认与忙碌状态**

```ts
const deleteTarget = ref<ModelProfile | null>(null);
const deletingId = ref<string | null>(null);
```

将 `remove(item)` 改为只清空旧错误并设置 `deleteTarget`，当前模型仍直接返回。

- [x] **Step 2: 实现确认删除函数**

```ts
async function confirmRemove() {
  const target = deleteTarget.value;
  if (!target || target.is_current || deletingId.value) return;
  deletingId.value = target.id;
  error.value = "";
  try {
    models.value = await deleteModelProfile(target.id);
    deleteTarget.value = null;
  } catch (reason) {
    deleteTarget.value = null;
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    deletingId.value = null;
  }
}
```

删除成功只使用服务返回列表；失败清空待确认目标、保留列表并显示错误，用户可再次点击删除重新确认。

- [x] **Step 3: 更新删除按钮与确认对话框模板**

删除按钮仅在 `v-else` 分支出现，增加 `:disabled="Boolean(deleteTarget || deletingId)"` 或等价的目标行状态；在模型管理 section 内增加 `v-if="deleteTarget"` 的 `alertdialog`，包含模型名、取消按钮和确认按钮。确认按钮在 `deletingId` 时禁用并显示加载图标/“删除中”。遮罩点击只清空 `deleteTarget` 且不改变 `models`。

- [x] **Step 4: 运行目标测试确认 GREEN**

运行 `cd desktop && npx playwright test tests/visual/model-manager.spec.ts`，确认新增取消、成功、失败、重试、焦点和竞态用例通过。

### Task 3: 回归验证与文档检查

**Files:**
- Inspect: `desktop/src/components/ModelConfig/ModelManager.vue`
- Inspect: `desktop/tests/visual/model-manager.spec.ts`

- [x] **Step 1: 运行桌面构建**

运行 `cd desktop && npm run build`，确认 TypeScript 和 Vite 构建通过。

- [x] **Step 2: 运行相关 Playwright 回归**

运行模型管理相关测试以及 Issue #30 新增测试；记录既有环境/快照失败，不把无关基线修复混入本 PR。

- [x] **Step 3: 检查差异与范围**

运行 `git diff --check` 和 `git status --short`，确认仅包含组件、交互测试及本 Issue 的设计/计划文档，没有后端协议或凭据文件。

- [x] **Step 4: 提交**

使用带 `Signed-off-by` 的中文提交，例如：

```bash
git add desktop/src/components/ModelConfig/ModelManager.vue desktop/src/workbench.css desktop/tests/visual/model-manager.spec.ts desktop/tests/visual/fixtures/model-manager.html desktop/tests/visual/fixtures/model-manager.ts docs/superpowers/specs/2026-08-10-model-delete-confirmation-design.md docs/superpowers/plans/2026-08-10-model-delete-confirmation.md
git commit -s -m "fix: 为模型删除增加确认和失败状态"
```
