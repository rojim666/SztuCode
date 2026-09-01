@echo off
echo ========================================
echo   SztuCode 浏览器开发模式启动脚本
echo ========================================
echo.

echo [1/3] 构建 runtime...
cd /d "%~dp0.."
call npm run build --workspace @sztucode/runtime-ts
if errorlevel 1 (
    echo 构建失败！
    pause
    exit /b 1
)

echo.
echo [2/3] 启动 WebSocket 代理（含 daemon）...
cd /d "%~dp0"
start "SztuCode WebSocket Proxy" node ws-proxy.mjs

echo.
echo [3/3] 启动 Vite 开发服务器...
start "SztuCode Vite Dev" npx vite --port 5173

echo.
echo ========================================
echo   启动完成！
echo   请在浏览器中访问: http://localhost:5173
echo ========================================
echo.
pause
