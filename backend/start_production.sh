#!/bin/bash
# Production startup script for AI Agent Test Platform Backend

echo "Starting AI Agent Test Platform Backend in production mode..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements_prod.txt

# Set environment
export APP_ENV=production

# Initialize database
echo "Initializing database..."
python -c "from database import init_database; init_database()"

# Start the application
echo "Starting production server..."
echo "Backend will be available at: http://0.0.0.0:8000"
echo "API Documentation: http://0.0.0.0:8000/docs"
echo "Health Check: http://0.0.0.0:8000/health"
echo ""
echo "Press Ctrl+C to stop the server"

# Run with gunicorn for production (if installed) or uvicorn
if command -v gunicorn &> /dev/null; then
    gunicorn production_backend:app \
        --workers 4 \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:8000 \
        --timeout 120 \
        --access-logfile - \
        --error-logfile -
else
    uvicorn production_backend:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 4 \
        --log-level info
fi