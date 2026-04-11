#!/bin/bash
# P4Frame stop script — kills all running P4Frame components

stop_component() {
    local name="$1"
    local match="$2"

    if pgrep -f "$match" > /dev/null; then
        pkill -f "$match"
        echo "✓ $name stopped"
    else
        echo "- $name was not running"
    fi
}

stop_component "Media frame"     "media_frame.py"
stop_component "Web config"      "web/web.py"
stop_component "Video converter" "video_converter.py"
