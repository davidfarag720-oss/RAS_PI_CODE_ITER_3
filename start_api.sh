#!/bin/bash
#
# start_api.sh
# Startup script for Vegetable Processing System API
#

set -e

echo "=========================================="
echo "Vegetable Processing System - API Server"
echo "=========================================="
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo ""
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p /home/pi/vegetable-slicer/{data/cv_images,logs,models,assets/ui}

# Validate configuration
echo ""
echo "Validating configuration..."
python3 -c "
from backend.config.config_manager import ConfigManager
config = ConfigManager('config.json')
config.validate()
print('✓ Configuration valid')
"

# Start server
echo ""
echo "=========================================="
echo "Starting API server on http://0.0.0.0:8000"
echo "=========================================="
echo ""
echo "API Documentation: http://localhost:8000/docs"
echo "Health Check: http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop"
echo ""

uvicorn backend.api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info