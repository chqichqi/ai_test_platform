@echo off
echo Starting AI Agent Test Platform...
echo.

echo 1. Activating virtual environment...
call venv\Scripts\activate.bat

echo 2. Starting application...
echo    App: AI Agent Test Platform
echo    Env: development
echo    Port: 8000
echo.

echo 3. Application will start shortly...
echo    API Docs: http://localhost:8000/docs
echo    Health: http://localhost:8000/health
echo.

python run.py