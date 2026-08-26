# PyCharm 配置指南

## 问题
测试显示PyCharm没有使用虚拟环境，导致依赖无法导入。

## 解决方案

### 方法1：在PyCharm中配置Python解释器

1. **打开PyCharm设置**
   - File → Settings (Windows/Linux)
   - PyCharm → Preferences (macOS)

2. **配置Python解释器**
   - 左侧导航：Project → Python Interpreter
   - 点击齿轮图标 → Add

3. **添加虚拟环境解释器**
   - 选择 "Existing environment"
   - 点击 "..." 浏览按钮
   - 导航到：`ai-agent-test-platform/backend/venv/Scripts/python.exe`
   - 点击 OK

4. **应用更改**
   - 点击 OK 保存设置
   - PyCharm会重新索引项目

### 方法2：使用终端激活虚拟环境

1. **打开PyCharm终端**
   - View → Tool Windows → Terminal
   - 或点击底部工具栏的 Terminal 图标

2. **激活虚拟环境**
   ```bash
   venv\Scripts\activate.bat
   ```

3. **验证虚拟环境**
   ```bash
   python -c "import sys; print('Virtual env' if sys.prefix != sys.base_prefix else 'System Python')"
   ```

### 方法3：创建PyCharm运行配置

1. **创建运行配置**
   - Run → Edit Configurations
   - 点击 "+" → Python

2. **配置运行参数**
   - Name: `AI Agent Test Platform`
   - Script path: `D:\test-programs\opencode\ai-agent-test-platform\backend\run.py`
   - Python interpreter: 选择虚拟环境中的python.exe
   - Working directory: `D:\test-programs\opencode\ai-agent-test-platform\backend`

3. **环境变量**
   - 点击 "Environment variables"
   - 添加：`PYTHONPATH=项目根目录`

## 验证配置

配置完成后，运行以下命令验证：

```bash
# 在PyCharm终端中运行
python -c "
import sys
print('Python路径:', sys.executable)
print('是否在虚拟环境:', '是' if sys.prefix != sys.base_prefix else '否')

import fastapi
print('FastAPI版本:', fastapi.__version__)
"
```

预期输出：
```
Python路径: D:\test-programs\opencode\ai-agent-test-platform\backend\venv\Scripts\python.exe
是否在虚拟环境: 是
FastAPI版本: 0.128.8
```

## 运行应用

配置完成后，可以通过以下方式运行：

### 方式1：使用PyCharm运行按钮
- 打开 `run.py` 文件
- 点击右上角的绿色运行按钮
- 或右键 → Run 'run'

### 方式2：使用终端
```bash
# 确保虚拟环境已激活
venv\Scripts\activate.bat

# 运行应用
python run.py
```

### 方式3：使用脚本
```bash
# 运行启动脚本
start.bat
```

## 访问应用

应用启动后，访问：
- API文档: http://localhost:8000/docs
- 交互式API文档: http://localhost:8000/redoc
- 健康检查: http://localhost:8000/health

## 常见问题

### 1. PyCharm提示 "No module named 'fastapi'"
**原因**: PyCharm没有使用虚拟环境
**解决**: 按照上面的步骤配置Python解释器

### 2. 导入错误但终端可以运行
**原因**: PyCharm和终端使用不同的Python环境
**解决**: 统一使用虚拟环境

### 3. 代码补全不工作
**原因**: PyCharm没有正确索引虚拟环境
**解决**: 
1. File → Invalidate Caches → Invalidate and Restart
2. 重新配置Python解释器

### 4. 运行配置报错
**原因**: 工作目录或环境变量设置错误
**解决**: 检查运行配置中的工作目录和环境变量

## 项目结构说明

```
ai-agent-test-platform/backend/
├── venv/                    # Python虚拟环境（已创建）
│   └── Scripts/
│       └── python.exe      # 虚拟环境Python解释器
├── app/                    # 应用代码
├── requirements.txt        # 依赖列表
├── .env                   # 环境变量
├── run.py                 # 启动脚本
├── pycharm_test.py        # 测试脚本
└── PYCHARM_SETUP.md       # 本文档
```

## 下一步

1. 在PyCharm中配置虚拟环境解释器
2. 运行 `pycharm_test.py` 验证配置
3. 运行 `run.py` 启动应用
4. 访问 http://localhost:8000/docs 测试API