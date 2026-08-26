# AI Agent Test Platform - 快速启动指南

## 1. 在PyCharm中配置

### 步骤1: 设置Python解释器
1. 打开PyCharm
2. File → Settings → Project → Python Interpreter
3. 点击齿轮图标 → Add
4. 选择 "Existing environment"
5. 浏览到: `ai-agent-test-platform\backend\venv\Scripts\python.exe`
6. 点击 OK → Apply → OK

### 步骤2: 验证配置
在PyCharm中运行 `verify_pycharm.py`:
- 右键点击 `verify_pycharm.py` → Run 'verify_pycharm'
- 或打开文件，点击右上角的绿色运行按钮

预期输出:
```
SUCCESS: Project is ready to run in PyCharm!
```

## 2. 运行应用

### 方式1: 使用PyCharm运行
1. 打开 `run.py`
2. 点击右上角绿色运行按钮
3. 查看控制台输出

### 方式2: 使用终端
1. 打开PyCharm终端 (View → Tool Windows → Terminal)
2. 激活虚拟环境:
   ```bash
   venv\Scripts\activate.bat
   ```
3. 运行应用:
   ```bash
   python run.py
   ```

## 3. 访问应用

应用启动后，访问以下地址:

- **API文档**: http://localhost:8000/docs
- **交互式文档**: http://localhost:8000/redoc  
- **健康检查**: http://localhost:8000/health
- **API端点**: http://localhost:8000/api/v1

## 4. 测试API

### 用户注册
```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "Test123!",
    "full_name": "Test User"
  }'
```

### 用户登录
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "Test123!"
  }'
```

## 5. 项目结构

```
ai-agent-test-platform/backend/
├── venv/                    # Python虚拟环境
├── app/                    # 应用代码
│   ├── core/              # 核心模块
│   │   ├── config.py      # 配置管理
│   │   ├── database.py    # 数据库连接
│   │   ├── logger.py      # 日志系统
│   │   └── models/        # 数据模型
│   ├── api/               # API端点
│   │   └── api_v1/        # API v1版本
│   └── services/          # 业务服务
├── requirements.txt        # Python依赖
├── .env                   # 环境变量
├── run.py                 # 启动脚本
├── verify_pycharm.py      # 验证脚本
└── PYCHARM_SETUP.md       # PyCharm配置指南
```

## 6. 故障排除

### 问题1: "No module named 'fastapi'"
**原因**: PyCharm没有使用虚拟环境
**解决**: 重新配置Python解释器 (步骤1)

### 问题2: 应用启动失败
**检查**:
1. 虚拟环境是否激活
2. 依赖是否安装: `pip list | findstr fastapi`
3. 端口是否被占用: `netstat -ano | findstr :8000`

### 问题3: 数据库连接错误
**检查**:
1. `.env` 文件中的 `DATABASE_URL`
2. PostgreSQL是否运行
3. 数据库是否存在: `ai_agent_test`

### 问题4: PyCharm代码补全不工作
**解决**:
1. File → Invalidate Caches → Invalidate and Restart
2. 重新配置Python解释器

## 7. 开发命令

```bash
# 激活虚拟环境
venv\Scripts\activate.bat

# 安装依赖
pip install -r requirements.txt

# 运行测试
pytest

# 数据库迁移
alembic upgrade head

# 代码格式化
black app/
isort app/
```

## 8. 下一步

1. 配置PyCharm Python解释器
2. 运行 `verify_pycharm.py` 验证
3. 运行 `run.py` 启动应用
4. 访问 http://localhost:8000/docs 测试API
5. 开始Phase 1开发工作

## 技术支持

如果遇到问题:
1. 检查 `PYCHARM_SETUP.md` 中的详细指南
2. 运行验证脚本 `verify_pycharm.py`
3. 查看控制台错误信息
4. 检查虚拟环境状态