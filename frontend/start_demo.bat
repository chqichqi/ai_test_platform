@echo off
echo Starting AI Agent Test Platform Demo...
echo.

echo Opening browser to http://localhost:3000...
start http://localhost:3000

echo Starting Python HTTP server...
python serve.py

pause