@echo off
echo Activating Python virtual environment...
call venv\Scripts\activate.bat
echo Virtual environment activated!
echo.
echo To install dependencies, run:
echo pip install -r requirements.txt
echo.
echo To run the application, run:
echo python run.py
echo.
cmd /k