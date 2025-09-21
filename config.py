#!/usr/bin/env python3
# File: config.py
# Centralized configuration for P4Frame media display system

import os
from pathlib import Path

# === Display Settings ===
DISPLAY = {
    'screen_width': 1920,        # Default screen width in pixels
    'screen_height': 1080,       # Default screen height in pixels
    'fullscreen': True,          # Start in fullscreen mode
    'hide_cursor': True,         # Hide mouse cursor in kiosk mode
    'background_color': 'black', # Background color
}

# === Media Settings ===
MEDIA = {
    'media_directory': '/home/pi/Pictures',  # Main media directory
    'photo_delay': 5000,                     # Photo display time in milliseconds
    'refresh_interval': 300000,              # Check for new media every 5 minutes (ms)
    'supported_image_formats': ('.jpg', '.jpeg', '.png', '.bmp', '.gif'),
    'supported_video_formats': ('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v'),
}

# === Video Conversion Settings ===
VIDEO_CONVERSION = {
    'enabled': True,                    # Enable automatic video conversion
    'check_interval': 60,               # Check for new videos every N seconds
    'cpu_cores': 2,                     # CPU cores to use for conversion
    'delete_originals': True,           # Delete original videos after conversion
    'converted_subfolder': 'converted', # Subfolder for converted videos
    'tmp_extension': '.tmp',           # Use .temp instead of .tmp for Windows compatibility

    # FFmpeg settings
    'codec': 'libx264',                 # Video codec (H.264)
    'preset': 'faster',                 # Encoding speed preset
    'crf': 23,                          # Quality factor (lower = better, 23 is good balance)
    'max_bitrate': '2M',                # Maximum video bitrate
    'buffer_size': '4M',                # Video buffer size
    'audio_codec': 'aac',               # Audio codec
    'audio_bitrate': '128k',            # Audio bitrate
    'timeout': 3600,                    # Conversion timeout in seconds (1 hour)
}

# === Logging Settings ===
LOGGING = {
    'enabled': True,
    'log_directory': '/home/pi/P4Frame/logs/video_converter',
    'log_level': 'DEBUG',
    'log_to_console': True,
    'log_to_file': True,
}

# === Slideshow Settings (for standalone slideshow mode) ===
SLIDESHOW = {
    'batch_size': 10,           # Number of images to process per batch (affects startup time)
    'border_size': 30,          # Border size between images in pixels
    'border_height': 50,        # Fixed border height
    'adaptive_top_height': 60,  # Top border height (border_height + 10)
    'preload_ahead': True,      # Preload next batch while displaying current
    'show_progress': True,      # Show batch loading progress
}

# === Video Player Settings ===
VIDEO_PLAYER = {
    'enabled': True,            # Enable/disable video playback (slideshow only if False)
    'scale_factor': 0.9,        # Use 90% of screen for video display
    'vlc_options': '--no-xlib', # VLC instance options
}

# === System Settings ===
SYSTEM = {
    'virtual_display': ':0.0',  # Virtual display for headless operation
    'escape_key_exit': True,    # Allow Escape key to exit application
}

# === Service Settings (for systemd service) ===
SERVICE = {
    'user': 'pi',
    'group': 'pi',
    'working_directory': '/home/pi/P4Frame',
    'restart_on_failure': True,
    'restart_delay': 10,  # Seconds before restart
}

# === Development/Debug Settings ===
DEBUG = {
    'enabled': False,
    'verbose_logging': False,
    'show_fps': False,
    'show_media_info': True,
}

# === Memory Management Settings ===
MEMORY_MANAGEMENT = {
    'max_cached_images': 3,      # Limit cached combined images
    'image_cache_ttl': 600,      # Clear cache every 10 minutes (seconds)
    'force_gc_interval': 3600,   # Force garbage collection hourly (seconds)
    'enable_memory_monitoring': True,  # Monitor memory usage
    'memory_limit_mb': 600,      # Warn if memory exceeds this (MB)
}

# === Helper Functions ===
def get_media_directory():
    """Get the media directory path, with fallback options"""
    primary = MEDIA['media_directory']
    if os.path.exists(primary):
        return primary
    
    # Fallback options
    fallbacks = [
        os.path.expanduser('~/Pictures'),
        os.path.expanduser('~/Media'),
        './data',
        '.'
    ]
    
    for path in fallbacks:
        if os.path.exists(path):
            return path
    
    return primary  # Return primary even if it doesn't exist

def get_converted_directory():
    """Get the converted videos directory path"""
    media_dir = get_media_directory()
    return os.path.join(media_dir, VIDEO_CONVERSION['converted_subfolder'])

def get_log_directory():
    """Get the log directory path, create if needed"""
    log_dir = LOGGING['log_directory']
    parent_dir = os.path.dirname(log_dir)

    # Check if parent directory is writable
    if not os.access(parent_dir, os.W_OK):
        raise PermissionError(f"Cannot write to log directory parent: {parent_dir}. "
                            f"Current user: {os.getenv('USER', 'unknown')}, "
                            f"Configured log directory: {log_dir}")

    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def load_custom_config(config_file=None):
    """Load custom configuration from file if it exists"""
    if config_file is None:
        # Look for config in standard locations
        locations = [
            './p4frame.conf',
            os.path.expanduser('~/.p4frame.conf'),
            '/etc/p4frame/p4frame.conf'
        ]
        
        for loc in locations:
            if os.path.exists(loc):
                config_file = loc
                break
    
    if config_file and os.path.exists(config_file):
        import json
        try:
            with open(config_file, 'r') as f:
                custom = json.load(f)
                
            # Update configuration with custom values
            for section, values in custom.items():
                if section in globals() and isinstance(globals()[section], dict):
                    globals()[section].update(values)
                    
            print(f"Loaded custom configuration from {config_file}")
        except Exception as e:
            print(f"Error loading custom config: {e}")

# Auto-load custom config on import
load_custom_config()