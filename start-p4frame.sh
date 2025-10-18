#!/bin/bash
# P4Frame startup script
# Starts video converter in background and media frame interactively

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "P4Frame Startup Script"
echo "======================"

# Check if video converter is already running
if pgrep -f "video_converter.py" > /dev/null; then
    echo "✓ Video converter is already running"
else
    echo "Starting video converter in background..."
    # Create logs directory if it doesn't exist
    mkdir -p logs
    
    # Start video converter in background
    nohup python3 video_converter.py > logs/video_converter.log 2>&1 &
    
    # Wait a moment and check if it started
    sleep 2
    if pgrep -f "video_converter.py" > /dev/null; then
        echo "✓ Video converter started successfully"
    else
        echo "✗ Failed to start video converter"
        echo "Check logs/video_converter.log for errors"
        exit 1
    fi
fi

echo ""
echo "Starting media frame..."
echo "Press ESC to exit when running"
echo ""

# Start media frame interactively
python3 media_frame.py

echo ""
echo "Media frame stopped."
echo ""
echo "Video converter is still running in background."
echo "To stop it: pkill -f video_converter.py"
echo "To check status: ps aux | grep video_converter"