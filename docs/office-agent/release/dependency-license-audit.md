# 依赖与分发审计

本阶段新增/使用的办公相关依赖及许可证（版本来自当前安装树）：

| 包 | 版本 | 许可证 | 分发备注 |
|---|---:|---|---|
| `pdf-parse` | 2.4.5 | Apache-2.0 | 允许随项目分发，保留许可证声明 |
| `mammoth` | 1.12.2 | BSD-2-Clause | 允许随项目分发，保留版权/许可证 |
| `xlsx` | 0.18.5 | Apache-2.0 | 允许随项目分发，保留许可证声明 |
| `@xenova/transformers` | 2.17.2 | Apache-2.0 | 可选本地 embedding 运行时 |
| `fflate` | 0.8.3 | MIT | 现有根依赖，用于离线 DOCX fixture |

没有新增闭源 SDK、Office 软件或真实平台凭据。飞书适配目前为接口和 Fake adapter，未引入飞书 SDK。发布包仍需按仓库现有 LICENSE/NOTICE 流程汇总传递性依赖声明。
