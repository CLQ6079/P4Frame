#!/bin/bash
# P4Frame startup script
# Starts video converter in background and media frame interactively

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "P4Frame Startup Script"
echo "======================"

# Set DISPLAY if not already set (for headless/SSH operation)
if [ -z "$DISPLAY" ]; then
    echo "No DISPLAY set, using :0.0 (local display)"
    export DISPLAY=:0.0
fi

echo "Using DISPLAY: $DISPLAY"

# Create logs directory if it doesn't exist
mkdir -p logs

# Check if video converter is already running
if pgrep -f "video_converter.py" > /dev/null; then
    echo "✓ Video converter is already running"
else
    echo "Starting video converter in background..."
    nohup python3 video_converter.py --config p4frame_raspi4.conf > logs/video_converter.log 2>&1 &
    sleep 2
    if pgrep -f "video_converter.py" > /dev/null; then
        echo "✓ Video converter started successfully"
    else
        echo "✗ Failed to start video converter"
        echo "Check logs/video_converter.log for errors"
        exit 1
    fi
fi

# Check if web config server is already running
if pgrep -f "web/web.py" > /dev/null; then
    echo "✓ Web config server is already running"
else
    echo "Starting web config server in background..."
    nohup python3 web/web.py --conf p4frame_raspi4.conf > logs/web_config.log 2>&1 &
    sleep 1
    if pgrep -f "web/web.py" > /dev/null; then
        echo "✓ Web config server started (http://$(hostname -I | awk '{print $1}'):8080)"
    else
        echo "✗ Failed to start web config server"
        echo "Check logs/web_config.log for errors"
    fi
fi

echo ""
echo "Starting media frame..."
echo "Press ESC to exit when running"
echo ""

# Start media frame interactively with config
python3 media_frame.py --config p4frame_raspi4.conf

echo ""
echo "Media frame stopped."
echo ""
echo "Background services still running:"
echo "  Video converter: pkill -f video_converter.py"
echo "  Web config:      pkill -f web/web.py"
echo "To check status: ps aux | grep -E 'video_converter|web_config'"