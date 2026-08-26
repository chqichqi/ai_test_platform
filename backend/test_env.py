"""
Environment test script
"""

import sys
import os

# Add project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("=== AI Agent Test Platform - Environment Test ===")

try:
    # Test basic imports
    print("1. Testing basic imports...")
    import fastapi
    import sqlalchemy
    import pydantic
    import loguru
    print("   [OK] Basic dependencies imported")
    
    # Test configuration
    print("\n2. Testing configuration system...")
    # Set environment variables
    os.environ["DATABASE_URL"] = "sqlite:///./test.db"
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key"
    
    from app.core.config import settings
    print(f"   [OK] Configuration imported")
    print(f"   App: {settings.APP_NAME}")
    print(f"   Env: {settings.APP_ENV}")
    print(f"   Port: {settings.PORT}")
    
    # Test logger
    print("\n3. Testing logger system...")
    from app.core.logger import logger
    logger.info("Test log message")
    print("   [OK] Logger working")
    
    # Test database
    print("\n4. Testing database system...")
    from app.core.database import init_db, check_db_health
    
    # Create data directories
    os.makedirs("data", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    print("   Initializing database...")
    init_db()
    print("   [OK] Database initialized")
    
    if check_db_health():
        print("   [OK] Database connection OK")
    else:
        print("   [WARN] Database connection check failed")
    
    # Test API
    print("\n5. Testing API application...")
    from app.main import app
    print(f"   [OK] FastAPI app imported")
    print(f"   Title: {app.title}")
    print(f"   Version: {app.version}")
    
    print("\n" + "="*50)
    print("[SUCCESS] All tests passed!")
    print("\nStart commands:")
    print("1. python run.py")
    print("2. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
    print("\nAccess URLs:")
    print("- API Docs: http://localhost:8000/docs")
    print("- Health: http://localhost:8000/health")
    print("\nDefault user:")
    print("- Username: admin")
    print("- Password: admin123")
    
except ImportError as e:
    print(f"\n[ERROR] Import error: {e}")
    print("\nInstall missing dependencies:")
    print("pip install fastapi uvicorn sqlalchemy pydantic loguru pydantic-settings python-jose[cryptography] passlib[bcrypt] python-dotenv python-multipart")
    
except Exception as e:
    print(f"\n[ERROR] Error: {e}")
    import traceback
    traceback.print_exc()