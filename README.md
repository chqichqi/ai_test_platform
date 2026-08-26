# AI Agent 测试平台

基于AI Agent的自动化测试平台，支持功能测试、API测试、WEB UI测试的自动化生成和执行。

## 项目架构

### 技术栈
- **后端**: Python 3.9 + FastAPI + SQLAlchemy + LangChain
- **前端**: React 18 + TypeScript + Ant Design
- **数据库**: PostgreSQL + Redis + ChromaDB (向量数据库)
- **AI**: LangChain + OpenAI API + 本地LLM支持
- **测试**: Playwright + Pytest + Requests

### 核心功能
1. RAG知识库文档管理
2. AI自动生成测试用例
3. 功能测试/API测试/WEB UI测试
4. SKILLS管理系统
5. 权限管理和用户系统

## 快速开始

### 环境要求
- Python 3.9+
- Node.js 16+
- PostgreSQL 13+
- Redis 6+

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd ai-agent-test-platform
```

2. **后端环境配置**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

3. **前端环境配置**
```bash
cd frontend
npm install
```

4. **数据库初始化**
```bash
cd backend
alembic upgrade head
```

5. **启动服务**
```bash
# 启动后端
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 启动前端
cd frontend
npm start
```

## 项目结构

```
ai-agent-test-platform/
├── backend/                    # 后端代码
│   ├── app/                   # 应用主目录
│   │   ├── api/              # API路由
│   │   ├── core/             # 核心模块
│   │   └── middleware/       # 中间件
│   ├── tests/                # 测试代码
│   ├── alembic/              # 数据库迁移
│   └── logs/                 # 日志文件
├── frontend/                  # 前端代码
│   ├── src/                  # 源代码
│   └── public/               # 静态资源
├── data/                     # 数据存储
│   ├── uploads/              # 上传文件
│   ├── database/             # 数据库文件
│   └── vector_store/         # 向量存储
├── docs/                     # 项目文档
├── scripts/                  # 脚本文件
└── deploy/                   # 部署配置
```

## 开发指南

### 后端开发
1. 遵循PEP 8代码规范
2. 使用类型注解
3. 编写单元测试
4. 使用日志记录

### 前端开发
1. 使用TypeScript
2. 遵循ESLint规则
3. 组件化开发
4. 响应式设计

## API文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 许可证

MIT License