@echo off
REM Development startup script for Windows
echo Starting AI Agent Test Platform Backend in development mode...

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Please install Python 3.9 or higher.
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install minimal dependencies for development
echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn sqlalchemy python-jose[cryptography] passlib[bcrypt] python-dotenv

REM Set environment
set APP_ENV=development

REM Initialize database
echo Initializing database...
python -c "from database import init_database; init_database()"

REM Start the application
echo.
echo Starting development server...
echo Backend will be available at: http://localhost:8000
echo API Documentation: http://localhost:8000/docs
echo Health Check: http://localhost:8000/health
echo.
echo Press Ctrl+C to stop the server
echo.

REM Run with auto-reload for development
uvicorn production_backend:app --host 0.0.0.0 --port 8000 --reload --log-level info