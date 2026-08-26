@echo off
echo Testing if application can run...
echo.

echo Step 1: Activate virtual environment
call venv\Scripts\activate.bat

echo Step 2: Test basic imports
python -c "
import sys
print('Python:', sys.executable)
print('In virtual env:', 'Yes' if sys.prefix != sys.base_prefix else 'No')

import fastapi
print('FastAPI:', fastapi.__version__)

import sqlalchemy
print('SQLAlchemy:', sqlalchemy.__version__)

import pydantic
print('Pydantic:', pydantic.__version__)

print('All core imports: OK')
"

echo.
echo Step 3: Test app imports
python -c "
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app.core.config import settings
    print('Configuration: LOADED')
    
    from app.core.logger import setup_logger
    logger = setup_logger()
    print('Logger: SETUP')
    
    from app.core.database import Base, engine
    print('Database: IMPORTED')
    
    from fastapi import FastAPI
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
    
    @app.get('/health')
    def health_check():
        return {'status': 'healthy', 'app': settings.APP_NAME}
    
    print('FastAPI app: CREATED with health endpoint')
    print('SUCCESS: Application can run!')
    
except Exception as e:
    print('ERROR:', str(e))
    import traceback
    traceback.print_exc()
"

echo.
echo Step 4: Try to run the actual app (will timeout after 10 seconds)
timeout /t 10 /nobreak > nul
start python run.py

echo.
echo If you see no errors above, the application should be running.
echo Open browser to: http://localhost:8000/docs
echo.
pause