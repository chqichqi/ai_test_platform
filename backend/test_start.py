"""
测试启动脚本
"""

import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    # 测试导入配置
    from app.core.config import settings
    print("✅ 配置导入成功")
    print(f"应用名称: {settings.APP_NAME}")
    print(f"环境: {settings.APP_ENV}")
    print(f"数据库URL: {settings.DATABASE_URL}")
    
    # 测试导入日志
    from app.core.logger import logger
    print("✅ 日志系统导入成功")
    logger.info("日志系统测试成功")
    
    # 测试导入数据库
    from app.core.database import init_db, check_db_health
    print("✅ 数据库系统导入成功")
    
    # 初始化数据库
    print("正在初始化数据库...")
    init_db()
    print("✅ 数据库初始化成功")
    
    # 检查数据库连接
    if check_db_health():
        print("✅ 数据库连接正常")
    else:
        print("⚠️ 数据库连接检查失败")
    
    # 测试导入主应用
    from app.main import app
    print("✅ FastAPI应用导入成功")
    
    print("\n🎉 所有组件导入成功！")
    print("可以启动应用了：")
    print("python run.py")
    print("或")
    print("uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
    
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请检查依赖是否安装：")
    print("pip install fastapi uvicorn sqlalchemy pydantic loguru python-jose[cryptography] passlib[bcrypt] python-dotenv python-multipart")
except Exception as e:
    print(f"❌ 其他错误: {e}")
    import traceback
    traceback.print_exc()