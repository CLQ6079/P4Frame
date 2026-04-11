#!/bin/bash
# P4Frame startup script
# Usage: bash start-p4frame.sh [config]
# Default config: p4frame_raspi4.conf

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONFIG="${1:-p4frame_raspi4.conf}"
VENV="$SCRIPT_DIR/.venv/bin/python3"
PYTHON="${VENV:-python3}"

echo "P4Frame Startup"
echo "==============="
echo "Config: $CONFIG"

# Set DISPLAY if not set (SSH operation)
if [ -z "$DISPLAY" ]; then
    export DISPLAY=:0.0
fi
echo "Display: $DISPLAY"
echo ""

# Start a component in nohup background, skip if already running
start_component() {
    local name="$1"
    local match="$2"
    local cmd="$3"

    if pgrep -f "$match" > /dev/null; then
        echo "✓ $name already running"
    else
        eval "nohup env DISPLAY=$DISPLAY $cmd > /dev/null 2>&1 &"
        sleep 1
        if pgrep -f "$match" > /dev/null; then
            echo "✓ $name started (PID $!)"
        else
            echo "✗ $name failed to start"
        fi
    fi
}

start_component "Video converter" "video_converter.py" \
    "$PYTHON video_converter.py --config $CONFIG"

start_component "Web config server" "web/web.py" \
    "$PYTHON web/web.py --conf $CONFIG"
echo "  Web UI: http://$(hostname -I | awk '{print $1}'):8080"

start_component "Media frame" "media_frame.py" \
    "$PYTHON media_frame.py --config $CONFIG"

echo ""
echo "All components started. Logs: $SCRIPT_DIR/logs/"
echo "To stop: bash stop-p4frame.sh"
