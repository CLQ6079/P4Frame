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
        
        # Video preloading - load, buffer, and pause ready videos
        self.preloaded_media = None
        self.preloaded_path = None
        self.preload_thread = None
        self.preloaded_ready = False  # True when video is loaded, buffered, and paused
        self.preloaded_frame_size = None  # Store calculated frame dimensions
        
        # Create main frame with white background
        self.main_frame = tk.Frame(root, bg='white', width=screen_width, height=screen_height)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.main_frame.pack_propagate(False)

        # Create video frame (centered)
        self.video_frame = tk.Frame(self.main_frame, bg='white')
        self.video_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        # Use singleton VLC instance
        self.instance = get_vlc_instance()
        self.player = self.instance.media_player_new()
        
        # Event manager for video end detection
        self.event_manager = self.player.event_manager()
        self.event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_video_ended)
        
    def preload_video(self, video_path):
        """Preload, buffer, and pause video for instant playback"""
        if not os.path.exists(video_path):
            return
            
        def _preload():
            try:
                # Create media
                media = self.instance.media_new(video_path)
                media.parse()
                time.sleep(0.1)
                
                # Set media to player
                self.player.set_media(media)
                
                # Set video output to our frame
                if os.name == 'nt':  # Windows
                    self.player.set_hwnd(self.video_frame.winfo_id())
                else:  # Linux/Mac
                    self.player.set_xwindow(self.video_frame.winfo_id())
                
                # Start playing to trigger buffering and dimension detection
                self.player.play()
                time.sleep(0.3)  # Give VLC time to start and buffer
                
                # Get video dimensions after playing starts
                video_width = self.player.video_get_width() or 1920
                video_height = self.player.video_get_height() or 1080
                
                # Calculate scaling
                scale_factor = config.VIDEO_PLAYER['scale_factor']
                scale_x = self.screen_width * scale_factor / video_width
                scale_y = self.screen_height * scale_factor / video_height
                scale = min(scale_x, scale_y)
                
                frame_width = int(video_width * scale)
                frame_height = int(video_height * scale)
                
                # Resize video frame while playing
                self.video_frame.configure(width=frame_width, height=frame_height)
                
                # Pause the video (keeps it buffered and ready)
                self.player.pause()
                
                # Hide the video frame until needed
                self.main_frame.pack_forget()
                
                # Store preload info
                self.preloaded_media = media
                self.preloaded_path = video_path
                self.preloaded_ready = True
                self.preloaded_frame_size = (frame_width, frame_height)
                
                if config.DEBUG.get('verbose_logging', False):
                    print(f"Preloaded and buffered video: {os.path.basename(video_path)} ({frame_width}x{frame_height})")
                    
            except Exception as e:
                print(f"Error preloading video {video_path}: {e}")
                self.preloaded_ready = False
                
        # Run preloading in background thread
        self.preload_thread = threading.Thread(target=_preload, daemon=True)
        self.preload_thread.start()
    
    def play_video(self, video_path, on_complete=None):
        """Play a video file instantly if preloaded, or normally if not"""
        if not os.path.exists(video_path):
            print(f"Video file not found: {video_path}")
            if on_complete:
                on_complete()
            return
            
        self.current_video = video_path
        self.on_complete_callback = on_complete
        
        # Check if video is preloaded and ready
        if (self.preloaded_path == video_path and self.preloaded_ready and 
            self.preloaded_media and self.preloaded_frame_size):
            
            # Video is preloaded, buffered, and paused - just show and unpause!
            frame_width, frame_height = self.preloaded_frame_size
            
            # Show video frame (already sized correctly)
            self.main_frame.pack(fill=tk.BOTH, expand=True)
            
            # Resume playback (video is already loaded and buffered)
            self.player.pause()  # Toggle pause (unpause)
            
            # Clear preload state
            self.preloaded_media = None
            self.preloaded_path = None
            self.preloaded_ready = False
            self.preloaded_frame_size = None
            
            if config.DEBUG.get('verbose_logging', False):
                print(f"Instant playback of preloaded video: {os.path.basename(video_path)}")
                
        else:
            # Fallback to normal loading if preload not available
            if config.DEBUG.get('verbose_logging', False):
                print(f"Normal loading for video: {os.path.basename(video_path)}")
                
            media = self.instance.media_new(video_path)
            media.parse()
            time.sleep(0.1)
            
            self.player.set_media(media)
            
            # Set video output
            if os.name == 'nt':  # Windows
                self.player.set_hwnd(self.video_frame.winfo_id())
            else:  # Linux/Mac
                self.player.set_xwindow(self.video_frame.winfo_id())
            
            # Get dimensions and scale
            video_width = self.player.video_get_width() or 1920
            video_height = self.player.video_get_height() or 1080
            
            scale_factor = config.VIDEO_PLAYER['scale_factor']
            scale_x = self.screen_width * scale_factor / video_width
            scale_y = self.screen_height * scale_factor / video_height
            scale = min(scale_x, scale_y)
            
            frame_width = int(video_width * scale)
            frame_height = int(video_height * scale)
            
            self.video_frame.configure(width=frame_width, height=frame_height)
            
            # Show video frame
            self.main_frame.pack(fill=tk.BOTH, expand=True)
            
            # Start playing
            self.player.play()
        
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
        # Clean up preloaded media
        if self.preloaded_media:
            self.preloaded_media = None
        self.preloaded_path = None
        self.preloaded_ready = False
        self.preloaded_frame_size = None
        
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