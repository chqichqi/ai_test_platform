@echo off
echo Installing core dependencies...
echo.

echo Step 1: Activating virtual environment...
call venv\Scripts\activate.bat

echo Step 2: Installing FastAPI and core dependencies...
pip install fastapi==0.104.1 uvicorn[standard]==0.24.0 python-multipart==0.0.6

echo Step 3: Installing database dependencies...
pip install sqlalchemy==2.0.23 alembic==1.12.1 psycopg2-binary==2.9.9

echo Step 4: Installing authentication dependencies...
pip install python-jose[cryptography]==3.3.0 passlib[bcrypt]==1.7.4 cryptography==41.0.7

echo Step 5: Installing configuration and utility dependencies...
pip install pydantic==2.5.0 pydantic-settings==2.1.0 python-dotenv==1.0.0 loguru==0.7.2

echo Step 6: Installing HTTP and async dependencies...
pip install httpx==0.25.1 aiohttp==3.9.1 requests==2.31.0

echo Step 7: Installing testing dependencies...
pip install pytest==7.4.3 pytest-asyncio==0.21.1 pytest-cov==4.1.0

echo Step 8: Installing code quality tools...
pip install black==23.11.0 isort==5.12.0 flake8==6.1.0 mypy==1.7.0

echo.
echo Core dependencies installed successfully!
echo.
echo To install all dependencies (including AI/ML packages), run:
echo pip install -r requirements.txt
echo.
pause