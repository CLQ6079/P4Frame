# P4Frame Features

## Photo Features

### Smart Layout
Automatically arranges multiple photos per screen to maximize space utilization. The system intelligently groups photos together to make the best use of screen real estate.

### Automatic Orientation
Corrects photo rotation based on EXIF metadata, ensuring all photos are displayed in the correct orientation regardless of how they were taken.

### Responsive Scaling
Scales images to fit screen height while maintaining aspect ratios, preventing distortion while maximizing the visible area.

### Even Spacing
Distributes borders evenly between images for a clean, professional look.

## Video Features

### Alternating Display
Photos and videos alternate in the slideshow, providing visual variety and dynamic content presentation.

### Gradient Background
Videos play with a purple-blue gradient background, creating an aesthetic viewing experience.

### Background Conversion
A separate background process automatically converts any video format to H.264 for optimal playback performance.

### Audio Support
Videos play with full audio support, allowing for complete multimedia experiences.

### CPU Management
The conversion process uses 2 CPU cores for video conversion, leaving 2 cores available for smooth playback on Raspberry Pi.

### Auto-refresh
The system automatically detects new media files every 5 minutes, ensuring your content stays up-to-date without manual intervention.

## How It Works

### Media Organization
- Photos stay in the main directory
- Videos are automatically converted to H.264 and stored in the `converted/` folder
- Original videos are deleted after successful conversion to save storage space

### Display Logic
- Alternates between photo groups and videos
- Photos display for a configurable duration (default 5 seconds)
- Videos play once with audio, then automatically move to the next item

### Background Processing
- Video converter runs as a separate background process
- Uses 2 CPU cores, preserving performance for playback
- Converts videos to optimized H.264 format for smooth playback
- Optimized for continuous operation with automatic memory cleanup
- Comprehensive logging with automatic rotation
- Graceful error handling and recovery

## Controls

- **ESC**: Exit fullscreen/quit application
- Videos play automatically once with audio
- Photos display for the configured delay period