# Virtual Environment Setup

## 虚拟环境已创建

项目已经创建了Python虚拟环境，位于 `venv/` 目录。

## 使用方法

### 1. 激活虚拟环境

**Windows:**
```bash
venv\Scripts\activate.bat
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 2. 已安装的核心依赖

虚拟环境中已经安装了以下核心依赖：
- FastAPI 0.128.8
- SQLAlchemy 2.0.48
- Pydantic 2.12.5
- Loguru 0.7.3
- Uvicorn 0.39.0
- Alembic 1.16.5
- psycopg2-binary 2.9.11
- 其他相关依赖

### 3. 检查虚拟环境状态

运行以下命令检查虚拟环境是否激活：
```bash
python -c "import sys; print('Virtual env:' if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) else 'System Python')"
```

### 4. 运行应用

确保虚拟环境激活后，运行：
```bash
python run.py
```

### 5. 安装其他依赖

如果需要安装requirements.txt中的所有依赖（包括AI/ML包）：
```bash
pip install -r requirements.txt --index-url https://pypi.org/simple
```

## 常见问题

### 1. 如何确认使用的是虚拟环境？
- 命令行提示符前会显示 `(venv)`
- 运行 `which python` (Linux/Mac) 或 `where python` (Windows) 查看Python路径

### 2. 如何退出虚拟环境？
```bash
deactivate
```

### 3. 依赖安装失败？
如果遇到网络问题，可以：
1. 使用官方源：`--index-url https://pypi.org/simple`
2. 使用国内镜像：`--index-url https://pypi.tuna.tsinghua.edu.cn/simple`

### 4. 重新创建虚拟环境
如果需要重新创建虚拟环境：
```bash
# 删除旧的
rmdir /s venv  # Windows
rm -rf venv    # Linux/Mac

# 创建新的
python -m venv venv
```

## 项目结构

```
backend/
├── venv/                    # Python虚拟环境
├── app/                    # 应用代码
├── requirements.txt        # 依赖列表
├── pyproject.toml         # 项目配置
├── .env                   # 环境变量
├── run.py                 # 启动脚本
└── README_VENV.md        # 本文档
```

## 下一步

1. 激活虚拟环境
2. 运行 `python run.py` 启动开发服务器
3. 访问 http://localhost:8000/docs 查看API文档