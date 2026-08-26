@echo off
echo AI Agent测试平台 - 快速启动
echo.

echo 1. 检查Node.js版本...
node --version
if %ERRORLEVEL% NEQ 0 (
    echo 错误: 请先安装Node.js (版本 >= 16)
    pause
    exit /b 1
)

echo.
echo 2. 检查依赖安装...
if not exist node_modules (
    echo 依赖未安装，正在安装...
    call npm install
    if %ERRORLEVEL% NEQ 0 (
        echo 依赖安装失败
        pause
        exit /b 1
    )
)

echo.
echo 3. 启动开发服务器...
echo 访问地址: http://localhost:3000
echo 按 Ctrl+C 停止服务器
echo.

call npm start