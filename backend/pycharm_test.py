#!/usr/bin/env python3
"""Test script for PyCharm environment."""

import sys
import os

print("=" * 60)
print("PyCharm Environment Test")
print("=" * 60)

# 1. Check Python environment
print("\n1. Python Environment:")
print(f"   Executable: {sys.executable}")
print(f"   Version: {sys.version}")
print(f"   Prefix: {sys.prefix}")
print(f"   Base Prefix: {sys.base_prefix}")

# Check if in virtual environment
in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
print(f"   In Virtual Environment: {'YES' if in_venv else 'NO'}")

# 2. Check project structure
print("\n2. Project Structure:")
project_root = os.path.dirname(os.path.abspath(__file__))
print(f"   Project Root: {project_root}")

# Check important directories
dirs_to_check = [
    ("app/", "Main application"),
    ("app/core/", "Core modules"),
    ("app/api/", "API endpoints"),
    ("app/core/models/", "Database models"),
    ("venv/", "Virtual environment"),
]

for dir_path, description in dirs_to_check:
    full_path = os.path.join(project_root, dir_path)
    exists = os.path.exists(full_path)
    status = "EXISTS" if exists else "MISSING"
    print(f"   {dir_path:20} {description:30} [{status}]")

# 3. Check imports
print("\n3. Testing Imports:")

imports_to_test = [
    ("fastapi", "FastAPI framework"),
    ("sqlalchemy", "SQLAlchemy ORM"),
    ("pydantic", "Pydantic models"),
    ("loguru", "Loguru logging"),
    ("uvicorn", "Uvicorn server"),
    ("alembic", "Alembic migrations"),
    ("psycopg2", "PostgreSQL adapter"),
]

for module_name, description in imports_to_test:
    try:
        module = __import__(module_name)
        version = getattr(module, "__version__", "unknown")
        print(f"   {module_name:15} {description:30} [OK - v{version}]")
    except ImportError:
        print(f"   {module_name:15} {description:30} [MISSING]")
    except Exception as e:
        print(f"   {module_name:15} {description:30} [ERROR: {str(e)[:50]}]")

# 4. Check app imports
print("\n4. Testing App Imports:")

app_imports = [
    ("app.core.config.Settings", "Configuration"),
    ("app.core.logger.setup_logger", "Logger setup"),
    ("app.core.database.Base", "Database base"),
    ("app.core.database.engine", "Database engine"),
]

for import_path, description in app_imports:
    try:
        # Simple import test
        if import_path == "app.core.config.Settings":
            # Set minimal environment variables
            os.environ.update({
                "SECRET_KEY": "test-key-for-pycharm",
                "DATABASE_URL": "sqlite:///:memory:",
                "JWT_SECRET_KEY": "test-jwt-key"
            })
            from app.core.config import Settings
            settings = Settings()
            print(f"   {import_path:30} {description:20} [OK]")
        elif import_path == "app.core.logger.setup_logger":
            from app.core.logger import setup_logger
            logger = setup_logger()
            print(f"   {import_path:30} {description:20} [OK]")
        elif import_path == "app.core.database.Base":
            from app.core.database import Base
            print(f"   {import_path:30} {description:20} [OK]")
        elif import_path == "app.core.database.engine":
            from app.core.database import engine
            print(f"   {import_path:30} {description:20} [OK]")
    except Exception as e:
        print(f"   {import_path:30} {description:20} [ERROR: {str(e)[:50]}]")

# 5. Try to run a simple FastAPI app
print("\n5. Testing FastAPI Application:")

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    
    # Create a minimal app
    app = FastAPI(title="Test App", version="1.0.0")
    
    @app.get("/test")
    def test_endpoint():
        return {"status": "ok", "message": "FastAPI is working"}
    
    # Test the endpoint
    client = TestClient(app)
    response = client.get("/test")
    
    if response.status_code == 200:
        print("   FastAPI Application: [RUNNING - Endpoint test passed]")
    else:
        print(f"   FastAPI Application: [ERROR - Status code: {response.status_code}]")
        
except Exception as e:
    print(f"   FastAPI Application: [ERROR - {str(e)[:50]}]")

print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)

# Summary
print("\nSUMMARY:")
print("-" * 40)

if in_venv:
    print("✓ Virtual environment is active")
else:
    print("✗ WARNING: Not using virtual environment")
    print("  In PyCharm, set interpreter to: venv\\Scripts\\python.exe")

# Check if all core imports work
core_modules_ok = all([
    'fastapi' in sys.modules,
    'sqlalchemy' in sys.modules,
    'pydantic' in sys.modules,
    'loguru' in sys.modules
])

if core_modules_ok:
    print("✓ All core dependencies are installed")
else:
    print("✗ Some core dependencies are missing")

print("\nNext steps for PyCharm:")
print("1. File → Settings → Project → Python Interpreter")
print("2. Click gear icon → Add")
print("3. Select 'Existing environment'")
print("4. Browse to: ai-agent-test-platform\\backend\\venv\\Scripts\\python.exe")
print("5. Click OK and apply changes")