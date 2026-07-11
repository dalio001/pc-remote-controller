#!/bin/bash
set -e

echo "=========================================="
echo "   PC Remote Controller - Setup"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "[ERROR] Python is not installed!"
    echo "Please install Python 3.9 or higher:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "  Mac: brew install python3"
    echo "  Or download from https://www.python.org/downloads/"
    exit 1
fi

PYTHON_CMD=$(command -v python3 || command -v python)
echo "[OK] Python found: $PYTHON_CMD"
$PYTHON_CMD --version
echo ""

# Install dependencies
echo "Installing dependencies..."
$PYTHON_CMD -m pip install -r requirements.txt

echo ""
echo "=========================================="
echo "   Setup Complete!"
echo "=========================================="
echo ""
echo "To start the server, run:  ./run.sh"
echo ""
