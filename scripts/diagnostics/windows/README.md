# Windows 窗口诊断

[返回脚本索引](../../README.md)

这里保留桌面圆角与原生窗口排查时使用的脚本，不属于产品运行链或自动验收门禁。

## 用法

从仓库根目录执行：

```powershell
powershell -File scripts/diagnostics/windows/probe-window.ps1
node scripts/diagnostics/windows/analyze2.mjs 200 20 200 140
```

- `capture-window.ps1`：读取 `sztucode-desktop` 窗口并截屏。保留了原作者的固定本机输出路径，复用前需调整脚本末尾的保存路径。
- `probe-window.ps1`：读取原生窗口、DWM 和显示状态。
- `analyze-window.mjs`、`analyze2.mjs`、`analyze3.mjs`：用 Sharp 检查根目录 `app-window.png` 的像素；`analyze2` 的四个参数是 left、top、width、height。
- `probe-corners.mjs`、`probe2.mjs`：通过 Playwright 访问 `http://127.0.0.1:5173`，检查像素和 DOM 几何。需要已启动的桌面开发服务、可用的 Sharp 及 Playwright 浏览器。

这些工具需要各自的本地依赖和运行环境，本次整理只检查脚本语法与移动后的依赖路径。

## 历史输出

`archive/probe-out.txt`、`archive/win-out.txt` 是原先已入库的输出，保留为诊断背景，不代表当前窗口状态。
本次从根目录移走的三份本地 `.log` 保存在 `tmp/diagnostics/2026-09-30/`，该目录被 Git 忽略。
