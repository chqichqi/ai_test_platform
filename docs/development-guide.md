# AI Agent测试平台 - 开发指南

## 第一阶段完成情况

### ✅ 已完成功能

#### 1. 企业级项目架构
- 完整的目录结构设计
- 前后端分离架构
- 模块化代码组织
- 配置文件管理

#### 2. 后端基础架构
- **FastAPI应用框架**：高性能异步API框架
- **SQLAlchemy ORM**：数据库操作抽象层
- **Pydantic模型验证**：请求/响应数据验证
- **Alembic数据库迁移**：版本化数据库管理

#### 3. 日志管理系统
- **结构化日志**：JSON格式日志输出
- **日志轮转**：按大小和时间自动轮转
- **多级别日志**：DEBUG/INFO/WARNING/ERROR
- **分类日志**：API请求、数据库操作、文件操作、AI操作等
- **文件存储**：应用日志和错误日志分离

#### 4. 用户认证和权限系统
- **JWT令牌认证**：访问令牌和刷新令牌
- **RBAC权限控制**：基于角色的访问控制
- **细粒度权限**：菜单级 + 按钮级权限控制
- **用户管理**：注册、登录、密码重置
- **角色管理**：预定义角色（viewer/tester/project_manager/admin）
- **权限管理**：完整的权限定义和分配

#### 5. API设计规范
- **统一响应格式**：成功/错误响应标准化
- **RESTful API设计**：资源导向的API设计
- **OpenAPI文档**：自动生成API文档
- **异常处理**：统一的异常处理机制
- **中间件**：请求日志、安全头、CORS等

### 📁 项目结构

```
ai-agent-test-platform/
├── backend/                    # 后端代码
│   ├── app/                   # 应用主目录
│   │   ├── api/              # API路由
│   │   │   ├── api_v1/       # API v1版本
│   │   │   │   ├── endpoints/ # API端点
│   │   │   │   └── api.py    # 路由注册
│   │   ├── core/             # 核心模块
│   │   │   ├── config.py     # 配置管理
│   │   │   ├── database.py   # 数据库连接
│   │   │   ├── logger.py     # 日志管理
│   │   │   ├── models/       # 数据模型
│   │   │   ├── schemas/      # Pydantic模式
│   │   │   └── services/     # 业务服务
│   │   └── middleware/       # 中间件
│   ├── tests/                # 测试代码
│   ├── alembic/              # 数据库迁移
│   ├── logs/                 # 日志文件
│   ├── requirements.txt      # Python依赖
│   ├── pyproject.toml       # 项目配置
│   ├── .env.example         # 环境变量示例
│   └── run.py               # 启动脚本
├── frontend/                 # 前端代码
│   ├── src/                 # 源代码
│   │   ├── components/      # 组件
│   │   ├── pages/           # 页面
│   │   ├── hooks/           # React Hooks
│   │   ├── utils/           # 工具函数
│   │   ├── store/           # 状态管理
│   │   ├── api/             # API调用
│   │   └── styles/          # 样式文件
│   ├── package.json         # 前端依赖
│   └── tsconfig.json        # TypeScript配置
├── data/                    # 数据存储
│   ├── uploads/             # 上传文件
│   ├── database/            # 数据库文件
│   └── vector_store/        # 向量存储
├── docs/                    # 项目文档
├── scripts/                 # 脚本文件
└── deploy/                  # 部署配置
```

### 🔧 技术栈

#### 后端技术栈
- **Python 3.9+**: 主编程语言
- **FastAPI**: Web框架
- **SQLAlchemy**: ORM
- **PostgreSQL**: 主数据库
- **Redis**: 缓存和会话存储
- **JWT**: 认证令牌
- **Pydantic**: 数据验证
- **Loguru**: 日志管理
- **Alembic**: 数据库迁移

#### 前端技术栈
- **React 18**: UI框架
- **TypeScript**: 类型安全
- **Ant Design**: UI组件库
- **Redux Toolkit**: 状态管理
- **React Router**: 路由管理
- **Axios**: HTTP客户端
- **React Query**: 数据获取

### 🚀 快速开始

#### 1. 环境准备
```bash
# 克隆项目
git clone <repository-url>
cd ai-agent-test-platform

# 创建虚拟环境
cd backend
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

#### 2. 配置环境变量
```bash
# 复制环境变量文件
cp .env.example .env

# 编辑.env文件，配置数据库连接等
```

#### 3. 数据库初始化
```bash
# 初始化数据库表
python -c "from app.core.database import init_db; init_db()"

# 或使用Alembic迁移
alembic upgrade head
```

#### 4. 启动后端服务
```bash
# 开发模式
python run.py

# 或直接使用uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 5. 访问API文档
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

#### 6. 默认用户
- 用户名: admin
- 密码: admin123
- 角色: 系统管理员（拥有所有权限）

### 📊 数据库设计

#### 核心表结构
1. **用户系统**
   - `user`: 用户表
   - `role`: 角色表
   - `permission`: 权限表
   - `user_role`: 用户-角色关联
   - `role_permission`: 角色-权限关联

2. **权限控制**
   - 基于角色的访问控制（RBAC）
   - 菜单级权限控制
   - 按钮级权限控制
   - 数据行级权限控制

### 🔐 权限系统

#### 权限层级
1. **模块权限**: 控制左侧导航菜单显示
2. **页面权限**: 控制页面访问权限
3. **操作权限**: 控制按钮显示/隐藏（新增、删除、编辑等）
4. **数据权限**: 控制数据行级操作

#### 预定义角色
1. **viewer** (查看者): 只能查看，不能操作
2. **tester** (测试员): 可以执行测试，创建测试用例
3. **project_manager** (项目经理): 可以管理项目，审批测试
4. **admin** (系统管理员): 拥有所有权限

### 📝 API使用示例

#### 1. 用户登录
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

#### 2. 获取用户信息
```bash
curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer <access_token>"
```

#### 3. 获取用户权限菜单
```bash
curl -X GET "http://localhost:8000/api/v1/auth/menus" \
  -H "Authorization: Bearer <access_token>"
```

#### 4. 获取页面操作权限
```bash
curl -X GET "http://localhost:8000/api/v1/auth/page-permissions?page_path=/projects/list" \
  -H "Authorization: Bearer <access_token>"
```

### 🎯 下一阶段开发计划

#### 第二阶段：RAG知识库系统
1. **文档上传功能**
   - 支持多种格式（PDF、DOCX、TXT等）
   - 文件大小限制和类型验证
   - 分块上传和断点续传

2. **文档处理流水线**
   - 文本提取和清洗
   - 文档分块和向量化
   - 向量数据库存储（ChromaDB）

3. **知识检索系统**
   - 语义搜索
   - 关键词搜索
   - 混合检索策略

#### 第三阶段：测试用例管理
1. **测试用例CRUD**
   - 创建、读取、更新、删除测试用例
   - 测试用例版本管理
   - 测试用例导入/导出

2. **测试用例分类**
   - 功能测试
   - API测试
   - WEB UI测试
   - 性能测试

3. **测试执行引擎**
   - 测试计划调度
   - 测试结果收集
   - 测试报告生成

### 🔍 调试和监控

#### 日志查看
```bash
# 查看应用日志
tail -f backend/logs/app.log

# 查看错误日志
tail -f backend/logs/error.log
```

#### 健康检查
```bash
curl http://localhost:8000/health
```

#### 数据库连接检查
```python
from app.core.database import check_db_health
print(f"Database health: {check_db_health()}")
```

### 🐛 常见问题

#### 1. 数据库连接失败
- 检查PostgreSQL服务是否运行
- 检查DATABASE_URL配置是否正确
- 检查数据库用户权限

#### 2. JWT令牌无效
- 检查JWT_SECRET_KEY配置
- 检查令牌是否过期
- 检查令牌格式是否正确

#### 3. 权限问题
- 检查用户角色分配
- 检查权限配置
- 检查API端点权限要求

### 📞 技术支持

如有问题，请参考：
1. FastAPI文档: https://fastapi.tiangolo.com/
2. SQLAlchemy文档: https://docs.sqlalchemy.org/
3. Ant Design文档: https://ant.design/
4. 项目GitHub仓库: <repository-url>

---

**第一阶段总结**: 已完成基础B/S架构、日志系统、用户认证和权限管理，为后续RAG知识库和测试用例管理打下了坚实基础。