@echo off
echo Testing configuration...
echo.

echo Step 1: Activate virtual environment
call venv\Scripts\activate.bat

echo Step 2: Run configuration test
python test_config.py

echo.
pause