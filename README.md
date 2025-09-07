# P4Frame - Smart Media Frame for Raspberry Pi

A complete media display system for Raspberry Pi that combines photo slideshows with video playback, featuring intelligent layout and automatic video conversion.

## System Overview

P4Frame is a dual-component system:
1. **Smart Photo Slideshow** - Displays multiple photos per screen with intelligent layout
2. **Video Playback System** - Plays videos with aesthetic gradient backgrounds and automatic H.264 conversion

## Key Features

### Photo Features
- **Smart Layout**: Automatically arranges multiple photos per screen to maximize space utilization
- **Automatic Orientation**: Corrects photo rotation based on EXIF metadata
- **Responsive Scaling**: Scales images to fit screen height while maintaining aspect ratios
- **Even Spacing**: Distributes borders evenly between images for a clean look

### Video Features
- **Alternating Display**: Photos and videos alternate in the slideshow
- **Gradient Background**: Videos play with purple-blue gradient background
- **Background Conversion**: Separate process converts any video format to H.264
- **Audio Support**: Videos play with sound
- **CPU Management**: Uses 2 cores for conversion, leaving 2 for playback
- **Auto-refresh**: Detects new media every 5 minutes

## How It Works

1. **Media Organization**: 
   - Photos stay in main directory
   - Videos are converted to H.264 and stored in `converted/` folder
   - Original videos deleted after conversion to save space

2. **Display Logic**:
   - Alternates between photo groups and videos
   - Photos display for configurable duration (default 5 seconds)
   - Videos play once with audio then move to next item

3. **Background Processing**:
   - Separate process handles video conversion
   - Uses 2 CPU cores, preserving performance for playback
   - Converts videos to optimized H.264 format

4. **Autocap restarts**:
   The system is now optimized for weeks/months of continuous operation with:
   - Automatic memory cleanup
   - Resource limits enforcement
   - Weekly preventive restarts
   - Comprehensive logging with rotation
   - Graceful failure recovery

## Installation

See [SETUP.md](SETUP.md) for complete installation instructions on Raspberry Pi.

* Install everything
  sudo ./install-services.sh

* Start services
sudo systemctl start video-converter.service
systemctl --user start p4frame.service

* Monitor memory usage
systemctl status p4frame.service
journalctl --user -u p4frame.service -f

* Manual restart if needed
sudo systemctl restart video-converter.service
systemctl --user restart p4frame.service

### Controls
- **ESC**: Exit fullscreen/quit application
- Videos play once with audio
- Photos display for configured delay

## Configuration

- All Python files now import and use the config module
- Command-line arguments override config defaults        
- Support for custom JSON config files via --config flag

Usage Examples:

* Use defaults from config.py `python media_frame.py`
* Override with command line `python media_frame.py /custom/path --delay 10000`
* Use custom config file `python media_frame.py --config /etc/p4frame/custom.conf`
* Video converter with custom settings `python video_converter.py --interval 120 --cores 4`

## File Structure

```
/home/pi/Pictures/
├── photo1.jpg          # Original photos
├── photo2.png
├── video1.avi          # Original videos (deleted after conversion)
├── video2.mov
└── converted/          # Converted H.264 videos
    ├── video1_h264.mp4
    └── video2_h264.mp4
```
