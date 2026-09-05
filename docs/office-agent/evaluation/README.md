# 办公任务评测基础

三个场景使用 `samples/` 中可合法分发的 UTF-8 文本与 CSV。离线检查不调用模型或网络：

```bash
npm run office:eval
```

输出 `tmp/eval/office-baseline/report.json` 与 `summary.md`。真实模型端到端评测必须由后续 adapter 单独启用，并在报告中记录模型、版本、参数、耗时和成本。

场景 1 研究报告：输入 `sources/*.md`，预期包含带 source/page-or-section 引用的事实表；确定性检查引用存在、关键数字一致、冲突被标记；人工评审关注覆盖、引用准确性、中文表达。

场景 2 表格分析：输入 `sales.csv`，预期输出可复算汇总与图表数据；确定性检查行数、合计、缺失值和图表序列；人工评审关注口径、异常解释和可读性。

场景 3 可编辑产物：输入场景 2 的结果，预期 DOCX/PPTX；当前生成器未实现，离线命令只检查需求声明并报告 `unimplemented`，禁止伪造通过。人工评审标准已预留：文本/表格可编辑、来源保留、图表与数据一致。

索引测量可运行：

```bash
npx tsx --test packages/runtime-ts/tests/workspace-indexer.test.ts
```

该测试验证 XLSX 工作表定位、源文件版本哈希、增量替换与删除清理。扫描件若未配置 OCR 会显式失败并说明缺少 OCR 适配器。
