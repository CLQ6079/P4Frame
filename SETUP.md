# P4Frame Setup for Raspberry Pi 4

## Prerequisites

Install required packages on your Raspberry Pi:

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install dependencies
sudo apt-get install -y python3-pip python3-tk ffmpeg vlc

# Install Python packages
pip3 install Pillow python-vlc
```

## Installation

1. Clone or copy all files to your Pi:
```bash
# Default directory /home/pi/P4Frame
git clone <repo-url> /home/pi/P4Frame
```

2. Create necessary directories:
```bash
cd /home/pi/P4Frame
mkdir -p logs/video_converter
mkdir -p /home/pi/Pictures/converted
```

### Web Configuration UI

A built-in web server lets you view and edit all settings from any browser on the same network — no SSH required. Changes are saved to the conf file and `media_frame.py` restarts automatically.

```bash
# Start manually (or let start-p4frame.sh handle it)
python3 web/web.py --conf p4frame_raspi4.conf --port 8080
```

Then open `http://<pi-ip>:8080` in a browser.

## Running the Application

### Recommended: Use the startup script

```bash
cd /home/pi/P4Frame
./start-p4frame.sh
```

This starts all three services in the correct order:
1. **Video converter** — background service, converts new videos to H.264
2. **Web config server** — background service on port 8080
3. **Media frame** — fullscreen slideshow (foreground)

### Manual startup (interactive)

```bash
cd /home/pi/P4Frame

# Video converter
python3 video_converter.py --config p4frame_linux.conf
# Web config server
python3 web/web.py --conf p4frame_linux.conf
# Media frame (foreground)
python3 media_frame.py --config p4frame_linux.conf
```

## Monitoring and Status

### Check running processes
```bash
ps aux | grep -E "(media_frame|video_converter|web_config)"
```

### View logs
```bash
# Media frame output (if started with nohup)
tail -f /home/pi/P4Frame/logs/media_frame.log

# Video converter
tail -f /home/pi/P4Frame/logs/video_converter.log

# Web config server
tail -f /home/pi/P4Frame/logs/web_config.log
```

## Maintenance

### Stop all services
```bash
pkill -f media_frame.py
pkill -f video_converter.py
pkill -f web/web.py
```

## Controls

| Key | Action |
|-----|--------|
| **ESC** | Quit application |
| **Right arrow** / Volume Up | Skip to next media |
| **Left arrow** / Volume Down | Go to previous media |

## Auto-start on Boot (optional)

To start P4Frame automatically when the Pi boots, add a systemd service or cron job:

```bash
# Using cron (simplest)
crontab -e
# Add this line:
@reboot sleep 10 && DISPLAY=:0.0 /home/pi/P4Frame/start-p4frame.sh >> /home/pi/P4Frame/logs/startup.log 2>&1
```
