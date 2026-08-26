@echo off
echo Installing dependencies using official PyPI source...
echo.

echo Step 1: Activating virtual environment...
call venv\Scripts\activate.bat

echo Step 2: Upgrading pip...
python -m pip install --upgrade pip --index-url https://pypi.org/simple

echo Step 3: Installing core dependencies...
pip install fastapi uvicorn[standard] python-multipart --index-url https://pypi.org/simple

echo Step 4: Installing database dependencies...
pip install sqlalchemy alembic psycopg2-binary --index-url https://pypi.org/simple

echo Step 5: Installing authentication dependencies...
pip install python-jose[cryptography] passlib[bcrypt] cryptography --index-url https://pypi.org/simple

echo Step 6: Installing configuration and utility dependencies...
pip install pydantic pydantic-settings python-dotenv loguru --index-url https://pypi.org/simple

echo Step 7: Installing HTTP and async dependencies...
pip install httpx aiohttp requests --index-url https://pypi.org/simple

echo Step 8: Installing testing dependencies...
pip install pytest pytest-asyncio pytest-cov --index-url https://pypi.org/simple

echo Step 9: Installing code quality tools...
pip install black isort flake8 mypy --index-url https://pypi.org/simple

echo.
echo Core dependencies installed successfully!
echo.
echo To install all dependencies (including AI/ML packages), run:
echo pip install -r requirements.txt --index-url https://pypi.org/simple
echo.
pause