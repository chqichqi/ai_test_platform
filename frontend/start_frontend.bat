@echo off
echo Starting AI Agent Test Platform Frontend...
echo.

cd /d "%~dp0"

echo Checking Node.js version...
node --version

echo.
echo Installing dependencies if needed...
call npm install

echo.
echo Starting development server on port 3000...
echo Frontend will be available at: http://localhost:3000
echo.

npm run dev

pause