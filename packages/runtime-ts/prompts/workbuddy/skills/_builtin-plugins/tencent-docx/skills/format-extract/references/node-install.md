# Node.js ≥ 18 安装脚本（环境准备兜底）

> 仅在 `node -v` 返回 `command not found` 或版本 < 18 时执行。
> 多数环境已具备 Node.js，**请优先用 `node -v` 检测后再决定是否需要本脚本**。

---

## 跨平台自动安装

```bash
OS="$(uname -s 2>/dev/null || echo Windows)"
case "$OS" in
  Linux*)
    if command -v nvm >/dev/null 2>&1; then
      nvm install --lts
    elif command -v fnm >/dev/null 2>&1; then
      fnm install --lts
    else
      curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
      source "$HOME/.nvm/nvm.sh"
      nvm install --lts
    fi
    ;;
  Darwin*)
    if command -v brew >/dev/null 2>&1 && [ "$(brew list node 2>/dev/null)" ]; then
      brew upgrade node
    elif command -v nvm >/dev/null 2>&1; then
      nvm install --lts
    elif command -v fnm >/dev/null 2>&1; then
      fnm install --lts
    else
      curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
      source "$HOME/.nvm/nvm.sh"
      nvm install --lts
    fi
    ;;
  *)
    if command -v fnm >/dev/null 2>&1; then
      fnm install --lts
    elif command -v winget >/dev/null 2>&1; then
      winget install OpenJS.NodeJS.LTS
    else
      echo "❌ 无法自动安装 Node.js，请手动安装: https://nodejs.org/"
      exit 1
    fi
    ;;
esac
```

安装完成后重新执行 `node -v` 验证版本 ≥ 18.0.0。

---

## 为什么强制 Node ≥ 18

bundled CLI 依赖 Node 18+ 的 ESM 与 `structuredClone`、`fetch` 等原生 API。版本过低会在运行时直接抛 `SyntaxError` 或 `ReferenceError`，且这些错误对 Agent 来说难以自动定位根因——因此在进入 CLI 调用前就拦截掉版本问题，能显著降低失败成本。
