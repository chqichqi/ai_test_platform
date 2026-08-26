"""
直接启动应用测试
"""

import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("Starting AI Agent Test Platform...")

try:
    # 设置环境变量
    os.environ["DATABASE_URL"] = "sqlite:///./test.db"
    os.environ["SECRET_KEY"] = "test-secret-key-change-in-production"
    os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-change-in-production"
    
    # 导入应用
    from app.main import app
    
    print(f"App: {app.title}")
    print(f"Version: {app.version}")
    print(f"Docs: http://localhost:8000/docs")
    print(f"Health: http://localhost:8000/health")
    
    # 尝试启动
    import uvicorn
    print("\nStarting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    
    print("\nTroubleshooting:")
    print("1. Check if all dependencies are installed")
    print("2. Check database connection")
    print("3. Check environment variables")