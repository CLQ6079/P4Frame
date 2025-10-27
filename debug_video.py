#!/usr/bin/env python3
"""
Debug script for testing VideoPlayer functionality
Usage: python debug_video.py <video_file_path>
"""

import sys
import os
import tkinter as tk
import time
from pathlib import Path

# Add current directory to path to import local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from video_player_lib import VideoPlayer

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_video.py <video_file_path>")
        print("Example: python debug_video.py /path/to/video.mp4")
        sys.exit(1)
    
    video_path = sys.argv[1]
    
    if not os.path.exists(video_path):
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
    
    print("=== VideoPlayer Debug Tool ===")
    print(f"Video file: {video_path}")
    print(f"Config loaded from: {config.__file__}")
    print(f"VLC options: {config.VIDEO_PLAYER.get('vlc_options', 'None')}")
    print()
    
    # Create Tkinter root window
    root = tk.Tk()
    root.title("VideoPlayer Debug")
    root.geometry("800x600")
    root.configure(bg='black')
    
    # Create VideoPlayer instance
    print("Creating VideoPlayer...")
    video_player = VideoPlayer(root, 800, 600)
    
    # Show the video player frame
    print("Showing video player frame...")
    video_player.show()
    
    # Update GUI to ensure window is mapped
    root.update_idletasks()
    root.update()
    time.sleep(0.3)
    
    def on_video_complete():
        print("Video playback completed!")
        root.after(2000, root.quit)  # Exit after 2 seconds
    
    def start_video():
        print("Starting video playback...")
        video_player.play_video(video_path, on_video_complete)
    
    # Start video after a short delay
    root.after(500, start_video)
    
    # Add escape key to quit
    def on_escape(event):
        print("Escape pressed - quitting...")
        video_player.cleanup()
        root.quit()
    
    root.bind('<Escape>', on_escape)
    root.focus_set()
    
    print("Starting GUI loop...")
    print("Press Escape to quit")
    print()
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Interrupted by user")
    finally:
        print("Cleaning up...")
        video_player.cleanup()
        root.destroy()

if __name__ == "__main__":
    main()