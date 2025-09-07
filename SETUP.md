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
scp *.py *.sh *.service *.conf pi@raspberrypi:/home/pi/P4Frame/
```

2. Run the automated installation:
```bash
cd /home/pi/P4Frame
sudo ./install-services.sh
```

This script will automatically:
- Create necessary directories
- Install systemd services (both system and user)
- Set up log rotation
- Configure weekly restart cron job
- Set up 2GB swap file if needed
- Enable services for auto-start on boot

## Configuration

The system uses centralized configuration in `config.py`. You can:

### Auto-start Configuration

Services are automatically configured to start on boot after installation. The system includes:
- **Resource limits**: Memory capped at 600MB, CPU at 200%
- **Automatic restart**: Services restart on failure
- **Weekly restart**: Automatic restart every Sunday at 3 AM
- **Log rotation**: Automatic log cleanup

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

## Monitoring and Status

### Check Service Status
```bash
# Check video converter service status
sudo systemctl status video-converter.service

# Check main P4Frame service status
systemctl --user status p4frame.service

# Check if services are enabled for boot
sudo systemctl is-enabled video-converter.service
systemctl --user is-enabled p4frame.service
```

### View Logs
```bash
# Live service logs
journalctl -u video-converter.service -f
journalctl --user -u p4frame.service -f

# Converter logs (if available)
tail -f /var/log/video_converter/converter_*.log

# Weekly restart logs
tail -f /home/pi/logs/p4frame-restart.log
```

### Check Cron Job
```bash
# View installed cron jobs
crontab -l

# Check cron service status
sudo systemctl status cron
```

### Memory and Resource Usage
```bash
# Check memory usage
free -h

# Check systemd resource usage
systemctl --user show p4frame.service --property=MemoryCurrent,CPUUsageNSec

# View process information
ps aux | grep -E "(python|p4frame|vlc)"
```

## Maintenance

### Manual Service Control
```bash
# Stop services
sudo systemctl stop video-converter.service
systemctl --user stop p4frame.service

# Restart services
sudo systemctl restart video-converter.service
systemctl --user restart p4frame.service

# Disable auto-start (if needed)
sudo systemctl disable video-converter.service
systemctl --user disable p4frame.service
```

### Manual Weekly Restart
```bash
# Run weekly restart script manually
/home/pi/P4Frame/cron-restart.sh
```

## Controls

- **ESC**: Exit fullscreen/quit application
- Videos play once with audio
- Photos display for configured delay (default 5 seconds)