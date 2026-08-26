@echo off
chcp 65001 >nul
echo ========================================
echo AI Agent测试平台 - 依赖修复工具
echo ========================================
echo.

echo 1. 清理旧的node_modules...
if exist node_modules rmdir /s /q node_modules
if exist package-lock.json del package-lock.json

echo.
echo 2. 设置淘宝镜像...
call npm config set registry https://registry.npmmirror.com

echo.
echo 3. 安装依赖（请耐心等待，这需要几分钟）...
call npm install --legacy-peer-deps

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo ✅ 依赖安装成功！
    echo ========================================
    echo.
    echo 启动开发服务器命令：
    echo npm start
    echo.
    echo 访问地址：http://localhost:3000
) else (
    echo.
    echo ========================================
    echo ❌ 依赖安装失败
    echo ========================================
    echo.
    echo 请尝试：
    echo 1. 检查网络连接
    echo 2. 手动运行：npm install --force
    echo 3. 或运行：npm cache clean --force && npm install
)

echo.
pause