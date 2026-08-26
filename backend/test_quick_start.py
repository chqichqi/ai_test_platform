#!/usr/bin/env python
"""
快速启动测试
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_basic_imports():
    """测试基本导入"""
    print("测试基本模块导入...")
    
    try:
        # 测试核心配置
        from app.core.config import Settings
        print("[OK] 配置类导入成功")
        
        # 测试数据库
        from app.core.database import Base, engine
        print("[OK] 数据库模块导入成功")
        
        # 测试主应用
        from app.main import app
        print("[OK] FastAPI应用导入成功")
        
        # 测试路由
        from app.api.api_v1.api import api_router
        print("[OK] API路由导入成功")
        
        return True
        
    except ImportError as e:
        print(f"[ERROR] 导入失败: {e}")
        print(f"Python路径: {sys.path}")
        return False
    except Exception as e:
        print(f"[ERROR] 其他错误: {e}")
        return False

def test_dependencies():
    """测试依赖项"""
    print("\n测试依赖项...")
    
    dependencies = [
        ("fastapi", "FastAPI"),
        ("sqlalchemy", "SQLAlchemy"),
        ("pydantic", "Pydantic"),
        ("jose", "JWT"),
    ]
    
    all_ok = True
    for module, description in dependencies:
        try:
            __import__(module)
            print(f"[OK] {description} ({module}) 可用")
        except ImportError:
            print(f"[WARNING] {description} ({module}) 未安装")
            all_ok = False
    
    return all_ok

def main():
    """主测试函数"""
    print("=" * 60)
    print("AI Agent测试平台 - 快速启动测试")
    print("=" * 60)
    
    # 测试依赖项
    deps_ok = test_dependencies()
    
    # 测试导入
    imports_ok = test_basic_imports()
    
    print("\n" + "=" * 60)
    print("测试结果:")
    print("=" * 60)
    
    if deps_ok and imports_ok:
        print("[SUCCESS] 所有测试通过！应用可以启动。")
        print("\n启动命令:")
        print("  cd D:\\test-programs\\opencode\\ai-agent-test-platform\\backend")
        print("  python run.py")
        return 0
    elif not deps_ok:
        print("[WARNING] 依赖项未完全安装，但代码结构正确。")
        print("\n安装依赖:")
        print("  pip install -r requirements.txt")
        return 1
    else:
        print("[ERROR] 代码结构有问题，请检查错误。")
        return 2

if __name__ == "__main__":
    sys.exit(main())