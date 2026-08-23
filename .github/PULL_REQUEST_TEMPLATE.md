## Summary

<!-- 做了什么，为什么需要这项变化。 -->

## Behavior

<!-- 用户可见行为、协议、配置或数据格式如何变化。 -->

## Validation

<!-- 列出实际运行过的命令和结果；未运行的检查说明原因。 -->

```text
npm run typecheck
npm test
npm run build
npm run docs:protocol
npm run docs:links
```

如只修改 Skill 的 Python artifact helper，再补充该 Skill 文档要求的专项检查。

## Risk

<!-- 兼容性、安全、迁移、性能、回滚方式和剩余风险。 -->

## UI evidence

<!-- 涉及 TUI/桌面端视觉变化时提供截图或录屏；否则写 N/A。 -->

## Checklist

- [ ] 变更范围与关联 Issue 一致，没有混入无关重构。
- [ ] 没有提交凭据、日志、缓存、私有源码或本地评测产物。
- [ ] 已添加或更新与风险匹配的测试。
- [ ] 协议变化已重新生成 `docs/reference/wire-protocol.md`。
- [ ] 用户文档、配置示例和迁移说明已同步。
- [ ] 提交包含 `Signed-off-by`（DCO）。
