@echo off
echo 正在安装 AI Agent 测试平台前端依赖...
echo.

echo 清理旧的 node_modules...
if exist node_modules rmdir /s /q node_modules

echo 安装依赖...
call npm install

if %ERRORLEVEL% EQU 0 (
    echo.
    echo 依赖安装成功！
    echo.
    echo 启动开发服务器命令：
    echo npm start
) else (
    echo.
    echo 依赖安装失败，请检查网络连接或手动安装。
)