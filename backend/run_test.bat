@echo off
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Running test script...
python test_app.py

pause