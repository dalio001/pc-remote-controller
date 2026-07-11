#!/bin/bash

echo "=========================================="
echo "   PC Remote Controller - Starting..."
echo "=========================================="
echo ""
echo "Your PC will be accessible from your phone"
echo ""

PYTHON_CMD=$(command -v python3 || command -v python)

# Get the computer's IP address
if command -v ip &> /dev/null; then
    IP=$(ip route get 1 2>/dev/null | awk '{print $7; exit}')
elif command -v ifconfig &> /dev/null; then
    IP=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -n 1)
else
    IP="YOUR_PC_IP"
fi

echo "Starting server..."
echo ""
echo "=========================================="
echo "   OPEN THIS URL ON YOUR PHONE:"
echo "   http://${IP}:8080"
echo "=========================================="
echo ""

cd "$(dirname "$0")"
$PYTHON_CMD -m backend.main
