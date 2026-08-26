#!/usr/bin/env python3
"""Simple test script to verify virtual environment and imports."""

import sys
import os

print("Testing Python virtual environment...")
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")

# Check if we're in a virtual environment
if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    print("[OK] Running in a virtual environment")
else:
    print("[WARNING] Not running in a virtual environment")

print("\nTesting core imports...")

try:
    import fastapi
    print(f"[OK] FastAPI: {fastapi.__version__}")
except ImportError:
    print("[ERROR] FastAPI not installed")

try:
    import sqlalchemy
    print(f"[OK] SQLAlchemy: {sqlalchemy.__version__}")
except ImportError:
    print("[ERROR] SQLAlchemy not installed")

try:
    import pydantic
    print(f"[OK] Pydantic: {pydantic.__version__}")
except ImportError:
    print("[ERROR] Pydantic not installed")

try:
    import loguru
    print(f"[OK] Loguru: {loguru.__version__}")
except ImportError:
    print("[ERROR] Loguru not installed")

try:
    import uvicorn
    print(f"[OK] Uvicorn: {uvicorn.__version__}")
except ImportError:
    print("[ERROR] Uvicorn not installed")

try:
    import alembic
    print(f"[OK] Alembic: {alembic.__version__}")
except ImportError:
    print("[ERROR] Alembic not installed")

try:
    import psycopg2
    print(f"[OK] psycopg2: {psycopg2.__version__}")
except ImportError:
    print("[ERROR] psycopg2 not installed")

print("\nChecking app structure...")

app_dir = os.path.join(os.path.dirname(__file__), "app")
if os.path.exists(app_dir):
    print("[OK] App directory exists")
    
    # Check subdirectories
    for subdir in ["core", "api", "models", "services"]:
        subdir_path = os.path.join(app_dir, subdir)
        if os.path.exists(subdir_path):
            print(f"[OK] {subdir} directory exists")
        else:
            print(f"[WARNING] {subdir} directory missing")
else:
    print("[ERROR] App directory not found")

print("\nVirtual environment setup complete!")