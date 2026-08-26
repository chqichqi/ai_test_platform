@echo off
echo Testing with virtual environment...
echo.

echo 1. Activating virtual environment...
call venv\Scripts\activate.bat

echo 2. Testing Python environment...
python -c "import sys; print('Python:', sys.executable); print('In venv:', 'Yes' if sys.prefix != sys.base_prefix else 'No')"

echo.
echo 3. Testing configuration...
python test_config.py

echo.
echo 4. Testing imports...
python -c "
try:
    import fastapi
    print('FastAPI: OK')
except ImportError as e:
    print('FastAPI: MISSING -', e)

try:
    import sqlalchemy
    print('SQLAlchemy: OK')
except ImportError as e:
    print('SQLAlchemy: MISSING -', e)

try:
    import pydantic
    print('Pydantic: OK')
except ImportError as e:
    print('Pydantic: MISSING -', e)
"

echo.
echo 5. Testing if app can run...
python -c "
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app.core.config import settings
    print('Configuration: LOADED')
    
    from fastapi import FastAPI
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
    print('FastAPI app: CREATED')
    
    print('SUCCESS: Application can run!')
except Exception as e:
    print('ERROR:', str(e)[:100])
"

echo.
pause