# 办公连接器框架

## 当前实现

`packages/runtime-ts/src/connectors.ts` 定义统一 Connector 接口，并提供 `FakeFeishuConnector`：

- 授权、刷新、撤销、状态查询
- 搜索、读取、创建草稿、更新、提交
- 外部对象 ID、版本和幂等键
- 草稿创建后回读验证
- `ConnectorError` 错误分类
- 日志字段脱敏

`createAndVerifyDraft` 只执行创建草稿和回读验证，不执行提交/发布。真实发送必须由单独的显式操作调用，并绑定对象 ID、版本和授权范围。

## 真实飞书接入

当前仓库没有已验证的飞书 OAuth/API 客户端适配器，因此未声称真实平台验证通过。后续适配器应实现同一 `Connector` 接口，将 access/refresh token 放入现有安全配置存储，禁止写入事件或普通日志；HTTP 429/5xx 应映射为可重试错误，取消通过 `AbortSignal` 传播，分页游标不得丢失。

没有真实账户时运行：

```bash
npx tsx --test packages/runtime-ts/tests/connectors.test.ts
```

该测试只验证模拟适配器，不代表飞书平台连通性。
