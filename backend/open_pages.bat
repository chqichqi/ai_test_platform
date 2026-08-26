@echo off
echo Opening AI Agent Test Platform pages...
echo.

echo 1. 控制面板 (HTML界面)
start http://localhost:8000/

echo 2. API文档 (Swagger UI)
start http://localhost:8000/docs

echo 3. 交互式文档 (ReDoc)
start http://localhost:8000/redoc

echo 4. 健康检查
start http://localhost:8000/health

echo 5. 应用信息
start http://localhost:8000/info

echo 6. API状态
start http://localhost:8000/api/status

echo.
echo 所有页面已在新标签页中打开！
echo.
echo 其他可用页面:
echo - Ping测试: http://localhost:8000/ping
echo - 版本信息: http://localhost:8000/version
echo - 认证测试: http://localhost:8000/api/v1/auth/test
echo - 用户注册: http://localhost:8000/api/v1/auth/register
echo - 用户登录: http://localhost:8000/api/v1/auth/login
echo.
pause