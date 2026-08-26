#!/usr/bin/env python3
"""Simple verification script for PyCharm."""

import sys
import os

def check_python_environment():
    """Check if we're using the virtual environment."""
    print("Checking Python environment...")
    print(f"Python executable: {sys.executable}")
    print(f"Python prefix: {sys.prefix}")
    print(f"Python base prefix: {sys.base_prefix}")
    
    # Check if in virtual environment
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        print("STATUS: Using virtual environment - GOOD")
        return True
    else:
        print("STATUS: NOT using virtual environment - NEED TO CONFIGURE")
        print("\nTo fix in PyCharm:")
        print("1. File -> Settings -> Project -> Python Interpreter")
        print("2. Click gear icon -> Add")
        print("3. Select 'Existing environment'")
        print("4. Browse to: venv\\Scripts\\python.exe")
        print("5. Click OK and apply")
        return False

def check_dependencies():
    """Check if core dependencies are installed."""
    print("\nChecking dependencies...")
    
    dependencies = [
        ("fastapi", "FastAPI web framework"),
        ("sqlalchemy", "SQLAlchemy ORM"),
        ("pydantic", "Pydantic data validation"),
        ("loguru", "Loguru logging"),
        ("uvicorn", "Uvicorn ASGI server"),
        ("alembic", "Alembic database migrations"),
        ("psycopg2", "PostgreSQL adapter"),
    ]
    
    all_ok = True
    for module_name, description in dependencies:
        try:
            module = __import__(module_name)
            version = getattr(module, "__version__", "unknown")
            print(f"  {module_name:12} {description:30} [OK - v{version}]")
        except ImportError:
            print(f"  {module_name:12} {description:30} [MISSING]")
            all_ok = False
        except Exception as e:
            print(f"  {module_name:12} {description:30} [ERROR: {e}]")
            all_ok = False
    
    return all_ok

def check_app_structure():
    """Check if app structure is correct."""
    print("\nChecking app structure...")
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    required_dirs = [
        ("app", "Main application directory"),
        ("app/core", "Core modules"),
        ("app/api", "API endpoints"),
        ("app/core/models", "Database models"),
        ("venv", "Virtual environment"),
    ]
    
    all_ok = True
    for dir_name, description in required_dirs:
        dir_path = os.path.join(current_dir, dir_name)
        if os.path.exists(dir_path):
            print(f"  {dir_name:20} {description:30} [EXISTS]")
        else:
            print(f"  {dir_name:20} {description:30} [MISSING]")
            all_ok = False
    
    return all_ok

def test_fastapi():
    """Test if FastAPI can run."""
    print("\nTesting FastAPI...")
    
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        
        # Create minimal app
        app = FastAPI(title="Test", version="1.0")
        
        @app.get("/test")
        def test():
            return {"status": "ok"}
        
        # Test endpoint
        client = TestClient(app)
        response = client.get("/test")
        
        if response.status_code == 200:
            print("  FastAPI application test [PASSED]")
            return True
        else:
            print(f"  FastAPI application test [FAILED - Status: {response.status_code}]")
            return False
            
    except Exception as e:
        print(f"  FastAPI application test [ERROR - {e}]")
        return False

def main():
    print("=" * 60)
    print("PyCharm Configuration Verification")
    print("=" * 60)
    
    # Run checks
    env_ok = check_python_environment()
    deps_ok = check_dependencies()
    struct_ok = check_app_structure()
    
    # Only test FastAPI if dependencies are OK
    fastapi_ok = False
    if deps_ok:
        fastapi_ok = test_fastapi()
    
    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    checks = [
        ("Python Environment", env_ok),
        ("Dependencies", deps_ok),
        ("App Structure", struct_ok),
        ("FastAPI Test", fastapi_ok if deps_ok else "SKIPPED"),
    ]
    
    for check_name, status in checks:
        if status is True:
            status_str = "PASS"
        elif status is False:
            status_str = "FAIL"
        else:
            status_str = status
        print(f"  {check_name:20} [{status_str}]")
    
    print("\n" + "=" * 60)
    
    if all([env_ok, deps_ok, struct_ok]):
        if fastapi_ok or not deps_ok:
            print("SUCCESS: Project is ready to run in PyCharm!")
            print("\nTo run the application:")
            print("1. Open run.py")
            print("2. Click the green run button")
            print("3. Visit http://localhost:8000/docs")
        else:
            print("WARNING: Basic checks passed but FastAPI test failed.")
    else:
        print("ISSUES DETECTED: Please fix the configuration.")
        
        if not env_ok:
            print("\nPrimary issue: Not using virtual environment")
            print("Fix: Configure PyCharm to use venv\\Scripts\\python.exe")
        
        if not deps_ok:
            print("\nDependencies missing")
            print("Fix: Activate virtual environment and run: pip install -r requirements.txt")
    
    print("=" * 60)

if __name__ == "__main__":
    main()