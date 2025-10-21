# File: video_player_lib.py

import os
import vlc
import tkinter as tk
from PIL import ImageTk
import threading
import time
from pathlib import Path
import config
import gc

# Initialize X11 for threading before any VLC operations
try:
    import ctypes
    import ctypes.util
    
    # Load X11 library
    x11_lib = ctypes.util.find_library('X11')
    if x11_lib:
        x11 = ctypes.CDLL(x11_lib)
        # Initialize X11 threading support
        x11.XInitThreads()
        print("X11 threading initialized successfully")
    else:
        print("Warning: X11 library not found, threading may have issues")
except Exception as e:
    print(f"Warning: Could not initialize X11 threading: {e}")

# Singleton VLC instance to prevent recreation
_vlc_instance = None

def get_vlc_instance():
    """Get or create singleton VLC instance"""
    global _vlc_instance
    if _vlc_instance is None:
        _vlc_instance = vlc.Instance(config.VIDEO_PLAYER['vlc_options'])
    return _vlc_instance

class VideoPlayer:
    def __init__(self, root, screen_width, screen_height):
        self.root = root
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.current_video = None
        self.on_complete_callback = None
        
        # Create main frame with white background (initially hidden)
        self.main_frame = tk.Frame(root, bg='white', width=screen_width, height=screen_height)
        self.main_frame.pack_propagate(False)
        # Don't pack initially - will be shown when video plays
        print(f"[VideoPlayer] Initialized - frame created but hidden")

        # Create video frame (centered)
        self.video_frame = tk.Frame(self.main_frame, bg='white')
        self.video_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        # Use singleton VLC instance
        self.instance = get_vlc_instance()
        self.player = self.instance.media_player_new()
        
        # Event manager for video end detection
        self.event_manager = self.player.event_manager()
        self.event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_video_ended)
        
    def play_video(self, video_path, on_complete=None):
        """Play a video file with proper scaling"""
        print(f"[VideoPlayer] play_video called: {os.path.basename(video_path)}")

        if not os.path.exists(video_path):
            print(f"[VideoPlayer] ERROR: Video file not found: {video_path}")
            if on_complete:
                on_complete()
            return

        self.current_video = video_path
        self.on_complete_callback = on_complete
        print(f"[VideoPlayer] Video path exists, starting playback...")

        # Ensure the video frame is realized and has a valid window ID
        self.video_frame.update_idletasks()
        window_id = self.video_frame.winfo_id()
        print(f"[VideoPlayer] Window ID: {window_id}")

        # Create media
        media = self.instance.media_new(video_path)
        self.player.set_media(media)

        # Set the video output to our frame
        if os.name == 'nt':  # Windows
            self.player.set_hwnd(window_id)
            print(f"[VideoPlayer] Set Windows HWND: {window_id}")
        else:  # Linux/Mac
            self.player.set_xwindow(window_id)
            print(f"[VideoPlayer] Set X11 window: {window_id}")
        
        # Get video dimensions
        media.parse()
        time.sleep(0.1)  # Give VLC time to parse

        video_width = self.player.video_get_width()
        video_height = self.player.video_get_height()

        # If dimensions are not available, start playing to get them
        if not video_width or not video_height:
            print(f"[VideoPlayer] Dimensions not available after parse, starting playback...")
            self.player.play()
            time.sleep(0.3)  # Give VLC time to start
            video_width = self.player.video_get_width() or 1920
            video_height = self.player.video_get_height() or 1080
            print(f"[VideoPlayer] Got dimensions after play: {video_width}x{video_height}")
        else:
            print(f"[VideoPlayer] Got dimensions from parse: {video_width}x{video_height}")
        
        # Calculate scaling to fit screen while maintaining aspect ratio
        scale_factor = config.VIDEO_PLAYER['scale_factor']
        scale_x = self.screen_width * scale_factor / video_width
        scale_y = self.screen_height * scale_factor / video_height
        scale = min(scale_x, scale_y)
        
        frame_width = int(video_width * scale)
        frame_height = int(video_height * scale)
        
        # Resize video frame
        self.video_frame.configure(width=frame_width, height=frame_height)
        print(f"[VideoPlayer] Video frame resized to {frame_width}x{frame_height}")

        # Start playing (if not already playing from dimension detection)
        player_state = self.player.get_state()
        print(f"[VideoPlayer] Current player state: {player_state}")

        if player_state != vlc.State.Playing:
            self.player.play()
            print(f"[VideoPlayer] player.play() called - video should start playing")
        else:
            print(f"[VideoPlayer] Video already playing from dimension detection")

        # Give VLC a moment to start rendering
        time.sleep(0.1)
        
    def on_video_ended(self, event):
        """Called when video playback ends"""
        print(f"[VideoPlayer] on_video_ended event fired for: {os.path.basename(self.current_video) if self.current_video else 'unknown'}")
        if self.on_complete_callback:
            # Schedule callback in main thread
            print(f"[VideoPlayer] Scheduling on_complete callback")
            self.root.after(100, self.on_complete_callback)
        else:
            print(f"[VideoPlayer] No on_complete callback set")
    
    def stop(self):
        """Stop current video playback"""
        if self.player:
            self.player.stop()
    
    def pause(self):
        """Pause/resume video playback"""
        if self.player:
            self.player.pause()
    
    def show(self):
        """Show the video player frame"""
        if hasattr(self, 'main_frame'):
            self.main_frame.pack(fill=tk.BOTH, expand=True)
            self.main_frame.lift()  # Bring to front
            print(f"[VideoPlayer] Frame shown and lifted to front")

    def hide(self):
        """Hide the video player frame"""
        if hasattr(self, 'main_frame'):
            self.main_frame.pack_forget()
            print(f"[VideoPlayer] Frame hidden")
    
    def get_converted_videos(self, directory):
        """Get list of converted (H.264) video files"""
        video_extensions = config.MEDIA['supported_video_formats']
        converted_dir = os.path.join(directory, config.VIDEO_CONVERSION['converted_subfolder'])
        
        if not os.path.exists(converted_dir):
            return []
            
        videos = []
        for file in os.listdir(converted_dir):
            if file.lower().endswith(video_extensions) and not file.startswith('.'):
                videos.append(os.path.join(converted_dir, file))
        
        return sorted(videos)
    
    def cleanup(self):
        """Clean up resources"""
        if self.player:
            self.player.stop()
            self.player.release()
            self.player = None
        
        
        # Note: Don't release the singleton VLC instance
        # It will be reused for the lifetime of the application
        
        # Force garbage collection
        gc.collect()


class VideoConverter:
    """Handle video conversion to H.264 in background"""
    
    @staticmethod
    def get_unconverted_videos(directory):
        """Find videos that need conversion"""
        video_extensions = config.MEDIA['supported_video_formats']
        converted_dir = os.path.join(directory, config.VIDEO_CONVERSION['converted_subfolder'])
        
        unconverted = []
        for file in os.listdir(directory):
            if file.lower().endswith(video_extensions) and not file.startswith('.'):
                file_path = os.path.join(directory, file)
                # Check if already converted
                converted_path = os.path.join(converted_dir, f"{Path(file).stem}_h264.mp4")
                if not os.path.exists(converted_path):
                    unconverted.append(file_path)
        
        return unconverted
    
    @staticmethod
    def convert_video(input_path, output_dir, delete_original=None, cpu_cores=None):
        if delete_original is None:
            delete_original = config.VIDEO_CONVERSION['delete_originals']
        if cpu_cores is None:
            cpu_cores = config.VIDEO_CONVERSION['cpu_cores']
        """Convert a single video to H.264"""
        import subprocess
        
        os.makedirs(output_dir, exist_ok=True)
        
        filename = Path(input_path).stem
        output_path = os.path.join(output_dir, f"{filename}_h264.mp4")
        
        # FFmpeg command from configuration
        command = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', config.VIDEO_CONVERSION['codec'],
            '-preset', config.VIDEO_CONVERSION['preset'],
            '-crf', str(config.VIDEO_CONVERSION['crf']),
            '-c:a', config.VIDEO_CONVERSION['audio_codec'],
            '-b:a', config.VIDEO_CONVERSION['audio_bitrate'],
            '-threads', str(cpu_cores),
            '-y',                # Overwrite output
            output_path
        ]
        
        try:
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"Successfully converted: {input_path}")
                if delete_original:
                    os.remove(input_path)
                    print(f"Deleted original: {input_path}")
                return True
            else:
                print(f"Conversion failed for {input_path}: {result.stderr}")
                return False
        except Exception as e:
            print(f"Error converting {input_path}: {e}")
            return False
    
    @staticmethod
    def batch_convert(directory, delete_originals=None, cpu_cores=None):
        """Convert all videos in directory"""
        if delete_originals is None:
            delete_originals = config.VIDEO_CONVERSION['delete_originals']
        if cpu_cores is None:
            cpu_cores = config.VIDEO_CONVERSION['cpu_cores']
            
        converted_dir = os.path.join(directory, config.VIDEO_CONVERSION['converted_subfolder'])
        videos = VideoConverter.get_unconverted_videos(directory)
        
        print(f"Found {len(videos)} videos to convert")
        
        for video in videos:
            print(f"Converting: {video}")
            VideoConverter.convert_video(video, converted_dir, delete_originals, cpu_cores)
        
        print("Batch conversion complete")


def alternating_media_generator(image_files, video_files):
    """Generator that alternates between images and videos"""
    max_length = max(len(image_files), len(video_files))
    
    for i in range(max_length):
        # Yield image(s) if available
        if i < len(image_files):
            yield ('image', image_files[i])
        
        # Yield video if available  
        if i < len(video_files):
            yield ('video', video_files[i])