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

1. Copy all files to your Pi:
```bash
# Create directory
mkdir -p /home/pi/P4Frame

# Copy files (from your development machine)
scp *.py *.conf pi@raspberrypi:/home/pi/P4Frame/
```

2. Create necessary directories:
```bash
cd /home/pi/P4Frame
mkdir -p logs/video_converter
mkdir -p /home/pi/Pictures/converted
```

## Configuration

The system uses centralized configuration in `config.py`. You can customize settings by editing the file directly or using a custom JSON config file.

## File Organization

```
/home/pi/Pictures/
├── photo1.jpg          # Original photos
├── photo2.png
├── video1.avi          # Original videos (will be deleted after conversion)
├── video2.mov
└── converted/          # Converted H.264 videos
    ├── video1_h264.mp4
    └── video2_h264.mp4
```

## Running the Application

### Start Video Converter (Background)
```bash
cd /home/pi/P4Frame
nohup python3 video_converter.py > logs/video_converter.log 2>&1 &
```

### Start Media Frame (Interactive)
```bash
cd /home/pi/P4Frame
python3 media_frame.py
```

## Monitoring and Status

### Check Running Processes
```bash
# Check if video converter is running
ps aux | grep video_converter

# Check all P4Frame processes
ps aux | grep -E "(media_frame|video_converter)"
```

### View Logs
```bash
# Video converter logs
tail -f /home/pi/P4Frame/logs/video_converter/converter_*.log

# Background process log
tail -f /home/pi/P4Frame/logs/video_converter.log
```

### Memory and Resource Usage
```bash
# Check memory usage
free -h

# View process information
ps aux | grep -E "(python|media_frame|vlc)"

# Check system resources
top
```

## Maintenance

### Stop Processes
```bash
# Stop video converter
pkill -f video_converter.py

# Stop media frame (or press ESC key)
pkill -f media_frame.py
```

### Restart Video Converter
```bash
# Stop and restart video converter
pkill -f video_converter.py
cd /home/pi/P4Frame
nohup python3 video_converter.py > logs/video_converter.log 2>&1 &
```

## Controls

- **ESC**: Exit fullscreen/quit application
- Videos play once with audio
- Photos display for configured delay (default 5 seconds)