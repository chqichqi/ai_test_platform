@echo off
echo AI Agent Test Platform - Backend
echo ================================
echo.

echo 1. Activating virtual environment...
call venv\Scripts\activate.bat

echo 2. Checking Python environment...
python -c "import sys; print(f'Python: {sys.version}'); print(f'Executable: {sys.executable}')"

echo.
echo 3. Available commands:
echo    run        - Start the development server
echo    test       - Run tests
echo    migrate    - Run database migrations
echo    shell      - Open Python shell with app context
echo.

echo Enter command: 
set /p command=

if "%command%"=="run" (
    echo Starting development server...
    python run.py
) else if "%command%"=="test" (
    echo Running tests...
    pytest
) else if "%command%"=="migrate" (
    echo Running migrations...
    alembic upgrade head
) else if "%command%"=="shell" (
    echo Opening Python shell...
    python -c "from app.core.database import SessionLocal; session = SessionLocal(); print('Database session created')"
) else (
    echo Unknown command: %command%
)

pause