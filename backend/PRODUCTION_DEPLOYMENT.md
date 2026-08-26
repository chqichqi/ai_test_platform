# AI Agent Test Platform - 生产部署指南

## 📋 系统要求

### 硬件要求：
- CPU: 2核以上
- 内存: 4GB以上
- 存储: 10GB以上可用空间

### 软件要求：
- Python 3.9+
- Node.js 16+
- SQLite 3.35+ (或 PostgreSQL 12+)
- Git

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <项目地址>
cd ai-agent-test-platform

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 2. 后端部署

```bash
cd backend

# 安装依赖
pip install -r requirements_prod.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置你的配置

# 初始化数据库
python database.py

# 启动后端
# 开发模式：
python fixed_backend.py
# 或使用生产脚本：
start_production.bat  # Windows
./start_production.sh # Linux/Mac
```

### 3. 前端部署

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览生产版本
npm run preview
```

## ⚙️ 环境配置

### `.env` 文件配置：

```env
# 应用配置
APP_ENV=production
APP_NAME=AI Agent Test Platform
APP_VERSION=1.0.0

# 服务器配置
HOST=0.0.0.0
PORT=8000
RELOAD=false

# 数据库配置
DATABASE_URL=sqlite:///test_platform.db
# 或使用 PostgreSQL:
# DATABASE_URL=postgresql://user:password@localhost:5432/test_platform

# 安全配置
SECRET_KEY=your-secret-key-change-in-production
JWT_SECRET_KEY=your-jwt-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS配置
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

## 🗄️ 数据库配置

### SQLite (默认)：
```bash
# 数据库文件会自动创建在：
# backend/test_platform.db
```

### PostgreSQL (生产推荐)：
```sql
-- 创建数据库
CREATE DATABASE test_platform;

-- 创建用户
CREATE USER test_user WITH PASSWORD 'secure_password';

-- 授权
GRANT ALL PRIVILEGES ON DATABASE test_platform TO test_user;
```

## 🔐 安全配置

### 1. 生成安全密钥：
```bash
# 生成随机密钥
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. 更新 `.env` 文件：
```env
SECRET_KEY=生成的32位随机密钥
JWT_SECRET_KEY=另一个生成的32位随机密钥
```

### 3. 修改默认密码：
```python
# 在 backend/auth_utils.py 中修改默认用户密码
DEFAULT_USERS = [
    {
        "username": "admin",
        "email": "admin@yourcompany.com",
        "password": "你的强密码",  # 修改这里
        "role": "admin"
    }
]
```

## 🌐 网络配置

### Nginx 反向代理配置：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL 证书
    ssl_certificate /path/to/ssl/cert.pem;
    ssl_certificate_key /path/to/ssl/key.pem;
    
    # 前端静态文件
    location / {
        root /path/to/frontend/dist;
        try_files $uri $uri/ /index.html;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # 后端 API 代理
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket 支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    
    # 静态文件缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

## 🐳 Docker 部署

### Dockerfile (后端)：
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements_prod.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements_prod.txt

# 复制应用代码
COPY . .

# 创建非root用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "fixed_backend:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose 配置：
```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/test_platform
      - APP_ENV=production
    depends_on:
      - db
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
    restart: unless-stopped

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=test_platform
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
```

## 📊 监控与日志

### 日志配置：
```python
# 在 backend/fixed_backend.py 中添加日志配置
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
```

### 健康检查端点：
```bash
# 检查服务健康状态
curl http://localhost:8000/health

# 检查数据库连接
curl http://localhost:8000/api/v1/health/db
```

## 🔄 备份与恢复

### 数据库备份：
```bash
# SQLite 备份
cp backend/test_platform.db backend/test_platform.db.backup.$(date +%Y%m%d)

# PostgreSQL 备份
pg_dump -U postgres test_platform > backup_$(date +%Y%m%d).sql
```

### 恢复数据库：
```bash
# SQLite 恢复
cp backend/test_platform.db.backup backend/test_platform.db

# PostgreSQL 恢复
psql -U postgres test_platform < backup_file.sql
```

## 🚨 故障排除

### 常见问题：

1. **端口被占用**：
```bash
# 查找占用端口的进程
netstat -ano | findstr :8000
# 或
lsof -i :8000

# 终止进程
taskkill /PID <进程ID> /F  # Windows
kill -9 <进程ID>           # Linux/Mac
```

2. **数据库连接失败**：
```bash
# 检查数据库文件权限
ls -la backend/*.db

# 检查数据库连接
python -c "from database import engine; print(engine.connect())"
```

3. **前端无法访问**：
```bash
# 检查前端服务
curl -I http://localhost:3000

# 重启前端
cd frontend && npm run dev
```

4. **认证失败**：
```bash
# 重置管理员密码
python reset_admin_password.py
```

## 📈 性能优化

### 数据库优化：
```sql
-- 创建索引
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_tests_type ON tests(type);
```

### 应用优化：
```python
# 启用连接池
SQLALCHEMY_POOL_SIZE = 20
SQLALCHEMY_MAX_OVERFLOW = 40
SQLALCHEMY_POOL_RECYCLE = 3600
```

## 🔧 维护脚本

### 创建维护脚本 `maintenance.py`：
```python
#!/usr/bin/env python3
"""
系统维护脚本
"""
import sys
from database import SessionLocal, User, Document, Test

def cleanup_old_data(days=30):
    """清理30天前的数据"""
    # 实现数据清理逻辑
    pass

def reset_admin_password():
    """重置管理员密码"""
    # 实现密码重置逻辑
    pass

def export_data(format='json'):
    """导出数据"""
    # 实现数据导出逻辑
    pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python maintenance.py <命令>")
        print("命令: cleanup, reset-password, export")
        sys.exit(1)
    
    command = sys.argv[1]
    if command == "cleanup":
        cleanup_old_data()
    elif command == "reset-password":
        reset_admin_password()
    elif command == "export":
        export_data()
    else:
        print(f"未知命令: {command}")
```

## 📞 支持与联系

### 获取帮助：
1. 查看日志文件：`backend/app.log`
2. 检查API文档：`http://localhost:8000/docs`
3. 查看系统状态：`http://localhost:8000/health`

### 紧急联系方式：
- 系统管理员：admin@yourcompany.com
- 技术支持：support@yourcompany.com

## ✅ 部署检查清单

- [ ] 环境变量配置完成
- [ ] 数据库初始化完成
- [ ] 安全密钥已更新
- [ ] SSL证书已配置
- [ ] 防火墙规则已设置
- [ ] 备份策略已实施
- [ ] 监控系统已部署
- [ ] 文档已更新

---

**部署完成！** 系统现在可以通过 `http://your-domain.com` 访问。

默认管理员账号：
- 用户名：admin
- 密码：admin123 (请在生产环境中修改)