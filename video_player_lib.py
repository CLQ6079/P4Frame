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
except Exception as e:
    pass

# Singleton VLC instance to prevent recreation
_vlc_instance = None

def get_vlc_instance():
    """Get or create singleton VLC instance"""
    global _vlc_instance
    if _vlc_instance is None:
        vlc_args = config.VIDEO_PLAYER['vlc_options']

        # If empty, use minimal options for Raspberry Pi
        if not vlc_args:
            vlc_args = '--no-audio --verbose=2'

        _vlc_instance = vlc.Instance(vlc_args)
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

        # Create video frame - use full screen instead of centered
        self.video_frame = tk.Frame(self.main_frame, bg='black')
        self.video_frame.pack(fill=tk.BOTH, expand=True)

        # Use singleton VLC instance
        self.instance = get_vlc_instance()

        self.player = self.instance.media_player_new()

        # IMPORTANT: Don't set xwindow during init - wait until frame is visible
        # Otherwise VLC won't attach properly on Linux/Raspberry Pi

        # Event manager for video end detection
        self.event_manager = self.player.event_manager()
        self.event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_video_ended)
        
    def play_video(self, video_path, on_complete=None):
        """Play a video file - simplified version"""

        if not os.path.exists(video_path):
            if on_complete:
                on_complete()
            return

        self.current_video = video_path
        self.on_complete_callback = on_complete

        # Stop any currently playing video
        if self.player.is_playing():
            self.player.stop()
            time.sleep(0.1)

        # CRITICAL: Make sure the frame is visible BEFORE getting window ID
        # The window must be mapped for VLC to attach properly on Linux

        # Force the frame to be displayed and updated
        self.video_frame.update()
        time.sleep(0.1)  # Give X11 time to map the window

        window_id = self.video_frame.winfo_id()
        width = self.video_frame.winfo_width()
        height = self.video_frame.winfo_height()
        x = self.video_frame.winfo_x()
        y = self.video_frame.winfo_y()
        viewable = self.video_frame.winfo_viewable()


        # Create and set media
        media = self.instance.media_new(video_path)
        self.player.set_media(media)

        # Set video output window
        if os.name == 'nt':  # Windows
            self.player.set_hwnd(window_id)
        else:  # Linux/Mac (Raspberry Pi)
            self.player.set_xwindow(window_id)

        # Just play - no scaling, no resizing, keep it simple
        result = self.player.play()

        # Wait a bit and check state
        time.sleep(0.5)
        state = self.player.get_state()
        is_playing = self.player.is_playing()
        has_vout = self.player.has_vout()  # Check if video output is active
        
    def on_video_ended(self, event):
        """Called when video playback ends"""
        if self.on_complete_callback:
            # Schedule callback in main thread
            self.root.after(100, self.on_complete_callback)
    
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
            # Force GUI update to ensure window is mapped
            self.main_frame.update_idletasks()
            self.main_frame.update()

    def hide(self):
        """Hide the video player frame"""
        if hasattr(self, 'main_frame'):
            self.main_frame.pack_forget()
    
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