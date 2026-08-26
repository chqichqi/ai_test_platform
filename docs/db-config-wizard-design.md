# MySQL数据库配置向导功能设计文档

## 功能概述

**触发时机：** 项目首次启动时，检测数据库未配置则自动跳转配置向导页面
**目标：** 提供友好的可视化界面配置MySQL数据库连接

## 用户流程

```
用户访问系统
    │
    ▼
系统检查数据库配置状态
    │
    ├── 已配置 ───────────────┐
    │    跳转到登录页面        │
    │                         │
    └── 未配置 ───────────────┤
         跳转到配置向导页面     │
              │               │
              ▼               │
┌─────────────────────────┐   │
│   数据库配置向导页面      │   │
│                         │   │
│  步骤1: 选择数据库类型    │   │
│    ○ SQLite (简单测试)   │   │
│    ● MySQL (生产环境)    │   │
│                         │   │
│  [下一步]               │   │
└─────────────────────────┘   │
              │               │
              ▼               │
┌─────────────────────────┐   │
│   步骤2: 配置连接信息     │   │
│                         │   │
│  主机: [localhost    ]  │   │
│  端口: [3306         ]  │   │
│  数据库: [ai_test_platform]│ │
│  用户名: [root       ]  │   │
│  密码: [********     ]  │   │
│                         │   │
│  [测试连接]             │   │
│  状态: ✅ 连接成功      │   │
│                         │   │
│  [上一步] [初始化数据库] │   │
└─────────────────────────┘   │
              │               │
              ▼               │
┌─────────────────────────┐   │
│   步骤3: 初始化进度       │   │
│                         │   │
│  创建数据库... ✓         │   │
│  创建数据表... ✓         │   │
│  初始化基础数据... ✓     │   │
│                         │   │
│  [完成] 跳转到登录页      │◄──┘
└─────────────────────────┘
```

## 后端API设计

### 1. 检查数据库配置状态
```http
GET /api/v1/system/db-config/status

Response:
{
  "configured": false,  // true: 已配置, false: 未配置
  "db_type": null,      // sqlite/mysql/null
  "message": "数据库未配置"
}
```

### 2. 测试数据库连接
```http
POST /api/v1/system/db-config/test

Request:
{
  "db_type": "mysql",
  "host": "localhost",
  "port": 3306,
  "database": "ai_test_platform",
  "username": "root",
  "password": "password"
}

Response:
{
  "success": true,
  "message": "连接成功",
  "version": "8.0.30",
  "existing_tables": []  // 已存在的表（用于检测是否已初始化）
}
```

### 3. 保存配置并初始化数据库
```http
POST /api/v1/system/db-config/init

Request:
{
  "db_type": "mysql",
  "host": "localhost",
  "port": 3306,
  "database": "ai_test_platform",
  "username": "root",
  "password": "password",
  "init_data": true  // 是否初始化基础数据
}

Response:
{
  "success": true,
  "message": "数据库初始化成功",
  "details": {
    "database_created": true,
    "tables_created": 28,
    "init_data_inserted": true
  }
}
```

### 4. SQLite快速配置
```http
POST /api/v1/system/db-config/quick-sqlite

Response:
{
  "success": true,
  "message": "SQLite配置成功",
  "db_path": "./data/app.db"
}
```

## 数据库表设计

### 系统配置表（存储数据库配置）
```sql
CREATE TABLE system_config (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value TEXT,
    is_encrypted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 存储数据库配置
INSERT INTO system_config (config_key, config_value, is_encrypted) VALUES
('db.type', 'mysql', FALSE),
('db.host', 'localhost', FALSE),
('db.port', '3306', FALSE),
('db.database', 'ai_test_platform', FALSE),
('db.username', 'root', FALSE),
('db.password', 'encrypted_password', TRUE);
```

## 前端页面设计

### 页面组件结构
```
DatabaseConfigWizard/
├── index.tsx                    # 主组件
├── steps/
│   ├── Step1_DatabaseType.tsx   # 步骤1: 选择数据库类型
│   ├── Step2_MySQLConfig.tsx    # 步骤2: MySQL配置
│   └── Step3_Initializing.tsx   # 步骤3: 初始化进度
├── components/
│   ├── ConnectionTest.tsx       # 连接测试组件
│   ├── ProgressPanel.tsx        # 进度面板
│   └── ConfigSummary.tsx        # 配置摘要
└── hooks/
    └── useDbConfig.ts           # 配置逻辑Hook
```

### 路由配置
```typescript
// 特殊路由，不需要登录
{ path: '/db-config', component: DatabaseConfigWizard, public: true }
```

### 权限控制
```typescript
// 数据库配置页面不需要登录
// 但已配置后再次访问应该重定向到登录页
```

## 后端实现细节

### 配置存储
- 数据库配置保存在 `.env` 文件或系统配置表中
- 密码使用 AES 加密存储
- 配置变更需要重启后端服务生效（或动态重载）

### 启动检查逻辑
```python
@app.on_event("startup")
async def startup_event():
    # 1. 检查数据库配置是否存在
    if not check_db_config():
        logger.warning("数据库未配置，等待用户配置...")
        app.state.db_configured = False
        return
    
    # 2. 尝试连接数据库
    try:
        init_db()
        app.state.db_configured = True
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        app.state.db_configured = False
```

### 中间件拦截
```python
@app.middleware("http")
async def db_config_check(request: Request, call_next):
    # 排除特定路径
    if request.url.path in ['/api/v1/system/db-config/status', 
                            '/api/v1/system/db-config/test',
                            '/api/v1/system/db-config/init']:
        return await call_next(request)
    
    # 检查数据库是否已配置
    if not app.state.db_configured:
        return JSONResponse(
            status_code=503,
            content={"code": "DB_NOT_CONFIGURED", "message": "数据库未配置"}
        )
    
    return await call_next(request)
```

## 错误处理

### 常见错误及提示
| 错误类型 | 用户提示 | 解决方案 |
|---------|---------|---------|
| 连接超时 | 无法连接到数据库服务器 | 检查主机地址和端口 |
| 认证失败 | 用户名或密码错误 | 检查凭据 |
| 数据库不存在 | 数据库不存在，是否创建？ | 提供创建选项 |
| 权限不足 | 用户权限不足 | 提示需要的数据库权限 |
| 版本过低 | MySQL版本需要8.0+ | 提示升级数据库 |

## 安全考虑

1. **密码加密** - 前后端传输和存储都加密
2. **配置隔离** - 配置信息不暴露在API响应中
3. **访问限制** - 仅在未配置时可访问配置页面
4. **重复配置** - 已配置后需要管理员权限才能修改

## 实现步骤

### Step 1: 后端API实现
1. 创建 `db_config.py` 服务模块
2. 实现配置检查、测试连接、初始化API
3. 修改启动逻辑，支持无数据库启动
4. 添加中间件拦截未配置状态

### Step 2: 前端页面实现
1. 创建数据库配置向导组件
2. 实现三步向导界面
3. 添加连接测试功能
4. 实现初始化进度显示

### Step 3: 路由和权限
1. 添加公开路由 `/db-config`
2. 前端路由守卫检查配置状态
3. 已配置后重定向到登录页

### Step 4: 测试
1. 测试未配置状态下的流程
2. 测试各种错误场景
3. 测试配置完成后的跳转
