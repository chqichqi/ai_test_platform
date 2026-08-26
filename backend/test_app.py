#!/usr/bin/env python3
"""Test script to verify the application can run."""

import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # Test imports
    print("Testing imports...")
    
    import fastapi
    print(f"[OK] FastAPI version: {fastapi.__version__}")
    
    import sqlalchemy
    print(f"[OK] SQLAlchemy version: {sqlalchemy.__version__}")
    
    import pydantic
    print(f"[OK] Pydantic version: {pydantic.__version__}")
    
    import loguru
    print(f"[OK] Loguru version: {loguru.__version__}")
    
    import uvicorn
    print(f"[OK] Uvicorn version: {uvicorn.__version__}")
    
    import alembic
    print(f"[OK] Alembic version: {alembic.__version__}")
    
    import psycopg2
    print(f"[OK] psycopg2 version: {psycopg2.__version__}")
    
    import pydantic_settings
    print(f"[OK] pydantic-settings version: {pydantic_settings.__version__}")
    
    print("\n[OK] All core dependencies imported successfully!")
    
    # Try to import our app modules
    print("\nTesting app modules...")
    
    # Import Settings without validation for testing
    import os
    os.environ.update({
        "SECRET_KEY": "test-secret-key",
        "DATABASE_URL": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-jwt-secret-key"
    })
    
    from app.core.config import Settings
    settings = Settings()
    print("[OK] Settings class imported and instantiated")
    
    from app.core.logger import setup_logger
    logger = setup_logger()
    print("[OK] Logger setup function imported and executed")
    
    from app.core.database import Base, engine
    print("[OK] Database Base and engine imported")
    
    print("\n[SUCCESS] Application is ready to run!")
    
except ImportError as e:
    print(f"\n[ERROR] Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] Error: {e}")
    sys.exit(1)