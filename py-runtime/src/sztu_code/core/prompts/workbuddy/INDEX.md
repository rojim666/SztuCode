# WorkBuddy 提示词合集（原样整理，仅供研究）

来源：docs/WorkBuddy/_analysis（5.4.7/5.5.4 解包）与 WorkBuddy-reference/extracted/cli/product.json。
本目录在 gitignore 区内，不入库（合规红线：prompt 原文不提交进仓库）。

## 01-主提示词-单体tpl（15 份）
旧架构单体模板：workbuddy-prompt.tpl 是主提示词（370 行 23 章）；
ask/craft/expert × code/coding/design 是场景×模式变体；
ask-mode-reminder / craft-mode-reminder 是模式切换时的覆盖声明（"This supersedes any other instructions"）；
user-context-identity / user-context-expert-identity 是身份注入段。

## 02-风格style（7 份）
7 种回复风格（专业/亲和/高效/创意/毒舌/苏格拉底/直白），同构四小节全文注入，
含"style affects HOW, not WHAT"元规则隔离事实层。

## 03-组合式fragments-interactionmode（30 个文件）
新架构组合式提示词：ask/craft/expert/plan 四模式各自的骨架 + fragments 片段目录。
craft/fragments/result-presentation.md 就是 HTML 一等产物那节；主提示词正往这套迁移。

## 04-技能skills（295 个 md）
19 个技能的 SKILL.md + references 提示材料（保留目录结构）。
重点看：library/SKILL.md（场景路由表）、tencent-docx/SKILL.md（根守门）
与其 skills/tdoc-orchestrator/SKILL.md（Stage 0 编排）、wb-finance-skill（46 篇 references）。

## 05-product模板-prompts（118 份）
product.json 云下发模板逐条拆出：
- tool-*-description：40+ 工具描述（含 tool-todowrite-description 双数组契约、tool-skill-description 技能索引形态）
- system-reminder-*：三层 reminder 的即时纠偏段
- 其余：compact/contextSummary 等内部 agent 提示词、commitMessage 等
清单：cli-agent-prompt、init-prompt、compact-agent-prompt、compact-prompt、context-summary-agent-prompt、context-summary-prompt、context-summary-max-token-prompt、command-security-review-prompt、command-commit-prompt、command-commit-push-pr-prompt、command-insights-prompt、base-agent-instructions、insights-facet-interaction-style、insights-facet-project-areas、insights-facet-friction、insights-facet-what-works、insights-facet-suggestions、insights-facet-opportunities、insights-facet-memorable-moment、insights-facet-at-a-glance、insights-session-facet、content-analyzer-agent-instructions、content-analyzer-prompt、terminal-title-generator-instructions、prompt-suggestion-instructions、memory-selector-instructions、summary-generator-instructions、auto-mode-classifier-instructions、auto-mode-critique-instructions、prompt-hook-evaluator-instructions、agent-instructions、system-reminder-md、system-reminder-todo-list、system-reminder-planmode、tool-agent-description、tool-bash-description、tool-powershell-description、tool-glob-description、tool-grep-description、tool-ls-description、tool-read-description、tool-edit-description、tool-multiedit-description、tool-write-description、tool-notebookread-description、tool-notebookedit-description、tool-webfetch-description、tool-listmcpresources-description、tool-readmcpresource-description、tool-waitformcpservers-description、tool-todowrite-description、tool-todowrite-planmode-result、tool-taskoutput-description、tool-taskcreate-description、tool-taskget-description、tool-taskupdate-description、tool-tasklist-description、tool-websearch-description、tool-enterplanmode-description、tool-enterplanmode-rejected、tool-enterplanmode-result、tool-exit-planmode-description、tool-exit-planmode-rejected、tool-exit-planmode-exited、tool-exit-planmode-resolve、tool-bashoutput-description、tool-killshell-description、tool-taskstop-description、tool-slashcommand-description、tool-skill-description、tool-skillmanage-description、agent-statusline-instructions、command-statusline-prompt、agent-explore-instructions、agent-plan-instructions、tool-ask-user-question-description、tool-lsp-description、tool-structuredoutput-description、tool-imagegen-description、tool-imageedit-description、tool-videogen-description、tool-artifact-description、tool-artifactcontrol-description、tool-computeruse-description、tool-teamcreate-description、tool-teamdelete-description、tool-sendmessage-description、team-sys-prompt、team-lead-prompt、system-reminder-delegate、output-style-explanatory、output-style-learning、cli-output-style-description、tool-toolsearch-description、tool-deferexecutetool-description、tool-describetool-description、tool-enterworktree-description、tool-croncreate-description、tool-crondelete-description、tool-cronlist-description、tool-delegatetool-description、skill-loop-prompt、workflow-tool-description、tool-repl-description、workflow-subagent-system-preamble、workflow-keyword-reminder、workflow-ultra-effort-active、workflow-ultra-effort-enter、workflow-ultra-effort-exit、deep-research-user-prompt、deep-research-trigger-reminder、deep-research-pending-reminder、simplify-trigger-reminder、code-review-trigger-reminder、verify-trigger-reminder、pulse-agent-prompt、handoff-summary-agent-prompt、enhance-prompt-system-prompt

## 06-内置子代理-agents（19 份）
product.json agents[] 的 instructions 逐条拆出（frontmatter 是我加的元信息，正文原样）：
cli、general-purpose、compact、contextSummary、contentAnalyzer、terminalTitleGenerator、promptSuggestion、memorySelector、summaryGenerator、autoModeClassifier、promptHookEvaluator、insightsAnalyzer、agentInstructions、statusline-setup、Explore、Plan、pulse、handoff-summary、enhance-prompt

