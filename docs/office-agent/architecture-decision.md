# 办公智能体架构决策

## 决策
生产内核继续采用现有 TypeScript runtime 作为新增办公产品行为的目标实现；保留 Python daemon 作为当前默认产品路径与兼容运行时。办公评测先使用无模型、无外部服务的独立 fixture harness，待能力真实接入后再挂接 `packages/evaluation` 的 runner。

## 保留模块
保留 `packages/protocol` 的 JSON-RPC/事件类型、`packages/runtime-ts` 的 workspace/session/agent/checkpoint/tool/provider、desktop 的 runtime service 与现有权限/Skills/MCP 边界。复用现有文档解析器、索引组件和 durable checkpoint，不复制 Python 产品逻辑。

## 迁移边界
新增 Office 行为（解析增强、表格分析、可编辑 DOCX/PPTX 产物、授权交付）写入 TS runtime 与 protocol；Python 只维持兼容与已存在能力。任何跨链调用必须通过已定义协议，不共享隐式文件状态。生成能力在有真实实现和验证器前标记未实现。

## 协议兼容
新增方法使用 `packages/protocol` 的显式版本字段、产物类型和来源引用；旧方法保持 JSON-RPC 2.0 NDJSON 形状。客户端遇到未知字段应忽略，未知方法返回标准错误。评测 fixture 不改变线上协议。

## 回滚
按能力开关关闭办公 workflow，保留原有 session/run 数据；产物写入独立 workspace 子目录。若 TS 能力失败，回退到原 agent 路径或人工交付，不自动把未验证的 Python 实现当作等价替代。协议变更采用新增方法/版本，禁止原地改变旧字段语义。

## 证据边界
当前测试证明解析器可读 PDF/DOCX/XLSX、checkpoint 可持久化写入、浏览器 MCP 存在测试；没有证明 PPTX 解析、Office 生成、CSV 分析编排、跨进程续跑、电脑控制 provider 或授权交付已可用。
