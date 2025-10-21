#!/usr/bin/env python3
# File: media_frame.py
# Main script for mixed photo/video slideshow

import os
import sys
import tkinter as tk
from slideshow_lib import get_image_files, create_combined_images, correct_orientation
from video_player_lib import VideoPlayer, alternating_media_generator
import argparse
from pathlib import Path
import config
import gc
import time
import logging

class MediaFrame:
    def __init__(self, root, media_dir=None, photo_delay=None, screen_width=None, screen_height=None):
        self.root = root
        self.media_dir = media_dir or config.get_media_directory()
        self.photo_delay = photo_delay or config.MEDIA['photo_delay']
        self.screen_width = screen_width or config.DISPLAY['screen_width']
        self.screen_height = screen_height or config.DISPLAY['screen_height']
        self.batch_size = config.SLIDESHOW.get('batch_size', 10)
        self.max_cache_size = config.MEMORY_MANAGEMENT.get('max_cached_images', 3)

        # Hide cursor for kiosk mode
        if config.DISPLAY['hide_cursor']:
            root.config(cursor="none")
        
        # Fullscreen
        if config.DISPLAY['fullscreen']:
            root.attributes('-fullscreen', True)
        root.configure(bg=config.DISPLAY['background_color'])
        
        # Bind escape key to exit
        if config.SYSTEM['escape_key_exit']:
            root.bind('<Escape>', lambda e: self.quit())
        
        # Bind volume keys for navigation with debouncing
        self.last_key_time = 0
        # Try to bind volume keys with error handling
        try:
            root.bind('<XF86AudioRaiseVolume>', self.on_volume_up)
            root.bind('<XF86AudioLowerVolume>', self.on_volume_down)
        except tk.TclError:
            try:
                # Alternative bindings for different systems
                root.bind('<AudioRaiseVolume>', self.on_volume_up)
                root.bind('<AudioLowerVolume>', self.on_volume_down)
            except tk.TclError:
                logging.warning("Warning: Could not bind volume keys, using only arrow keys")
        
        # Also bind arrow keys as fallback
        root.bind('<Right>', self.on_volume_up)
        root.bind('<Left>', self.on_volume_down)
        
        # Make sure the window can receive keyboard events
        root.focus_set()
        
        # Initialize timer tracking
        self._scheduled_after = None
        
        # Get media files
        self.all_image_files = get_image_files(self.media_dir)
        self.video_files = self.get_video_files()
        
        if config.DEBUG['show_media_info']:
            logging.info(f"Found {len(self.all_image_files)} images and {len(self.video_files)} videos")
            if len(self.all_image_files) > self.batch_size:
                total_batches = (len(self.all_image_files) + self.batch_size - 1) // self.batch_size
                logging.info(f"Will process in {total_batches} batches of up to {self.batch_size} images each")
        
        # Batch processing setup
        self.current_batch_index = 0
        self.combined_images = []  # Will be populated batch by batch
        self.preloaded_batch = None  # For preloading next batch
        
        # Process first batch of images
        self.process_next_batch()
        
        # Initialize components
        self.video_player = None
        if config.VIDEO_PLAYER.get('enabled', True):
            self.video_player = VideoPlayer(root, self.screen_width, self.screen_height)
        self.photo_label = tk.Label(root, bg='black')
        
        # Memory management
        self.current_photo = None  # Track current PhotoImage for cleanup
        self.last_gc_time = time.time()
        self.image_cache = []  # Track combined images for cleanup
        self.max_cache_size = config.MEMORY_MANAGEMENT.get('max_cached_images', 3)
        self.batch_cache = {}  # Cache processed batches
        
        # Create media queue (alternating photos and videos)
        self.media_queue = []
        self.create_media_queue()
        self.current_index = 0
        
        # Start slideshow
        self.show_next_media()
    
    def get_video_files(self):
        """Get converted video files"""
        converted_dir = os.path.join(self.media_dir, config.VIDEO_CONVERSION['converted_subfolder'])
        if not os.path.exists(converted_dir):
            return []
        
        videos = []
        for file in os.listdir(converted_dir):
            if file.lower().endswith(config.MEDIA['supported_video_formats']) and not file.startswith('.'):
                videos.append(os.path.join(converted_dir, file))
        
        return sorted(videos)
    
    def process_next_batch(self):
        """Process next batch of images"""
        start_idx = self.current_batch_index * self.batch_size
        end_idx = start_idx + self.batch_size
        
        # Get current batch of image files
        batch_files = self.all_image_files[start_idx:end_idx]
        
        if batch_files:
            if config.SLIDESHOW.get('show_progress', True) or config.DEBUG.get('verbose_logging', False):
                total_batches = (len(self.all_image_files) + self.batch_size - 1) // self.batch_size
                logging.info(f"Loading batch {self.current_batch_index + 1}/{total_batches}: {len(batch_files)} images...")
            
            # Create combined images for this batch only
            batch_combined = create_combined_images(
                batch_files,
                self.screen_width,
                self.screen_height
            )
            
            # Add to our collection
            self.combined_images.extend(batch_combined)
            
            # Clean up old batches if cache is full
            self.manage_batch_cache()
            
            if config.SLIDESHOW.get('show_progress', True):
                logging.info(f"Batch {self.current_batch_index + 1} ready ({len(batch_combined)} slides created)")
        
        return len(batch_files) > 0
    
    def manage_batch_cache(self):
        """Keep only recent batches in memory"""
        # Keep only the last N combined images
        max_combined = self.max_cache_size * 3  # Allow more since they're created on demand
        if len(self.combined_images) > max_combined:
            # Clean up old combined images
            old_images = self.combined_images[:-max_combined]
            for img in old_images:
                if img and hasattr(img, 'close'):
                    img.close()
            self.combined_images = self.combined_images[-max_combined:]
            gc.collect()
    
    def create_media_queue(self):
        """Create queue: play all photos in batch, then one video, repeat"""
        self.media_queue = []
        
        # Add all photos from current batch
        for photo_group in self.combined_images:
            self.media_queue.append(('photo', photo_group))
        
        # Add one video after the photo batch (if videos available)
        if self.video_files:
            # Use modulo to cycle through videos
            video_index = self.current_batch_index % len(self.video_files)
            self.media_queue.append(('video', self.video_files[video_index]))
    
    def show_next_media(self):
        """Display next media item in queue"""
        if not self.media_queue:
            logging.info("No media to display")
            return
        
        # Check if we need to load more batches
        if self.current_index > 0 and self.current_index % (self.batch_size // 2) == 0:
            # We're halfway through current batch, preload next batch
            self.preload_next_batch()
        
        # Check if we've reached the end of current queue
        if self.current_index >= len(self.media_queue):
            # Process next batch and recreate queue
            self.current_batch_index += 1
            if self.current_batch_index * self.batch_size >= len(self.all_image_files):
                # Wrap around to beginning
                self.current_batch_index = 0
                if config.DEBUG.get('verbose_logging', False):
                    logging.info("Restarting from first batch")
            
            if self.process_next_batch():
                self.create_media_queue()
                self.current_index = 0
            else:
                # No more images, just cycle existing
                self.current_index = 0
        
        # Get current media item
        media_type, media_item = self.media_queue[self.current_index]

        if media_type == 'photo':
            self.show_photo(media_item)
        elif media_type == 'video' and config.VIDEO_PLAYER.get('enabled', True):
            self.show_video(media_item)
        else:
            # Skip video if player disabled, move to next item
            self.current_index += 1
            self._scheduled_after = self.root.after(100, self.show_next_media)  # Quick transition to next
            return
        
        # Move to next item
        self.current_index += 1
    
    def preload_next_batch(self):
        """Preload next batch in background"""
        import threading
        
        def load_batch():
            next_batch_index = self.current_batch_index + 1
            start_idx = next_batch_index * self.batch_size
            end_idx = start_idx + self.batch_size
            
            if start_idx < len(self.all_image_files):
                batch_files = self.all_image_files[start_idx:end_idx]
                if batch_files and config.DEBUG.get('verbose_logging', False):
                    logging.info(f"Preloading batch {next_batch_index + 1}: {len(batch_files)} images")
        
        # Run in background thread to not block UI
        thread = threading.Thread(target=load_batch, daemon=True)
        thread.start()
    
    def show_photo(self, combined_image):
        """Display a combined photo image"""
        # Hide video player if it exists
        if self.video_player:
            self.video_player.main_frame.pack_forget()
        
        # Clean up previous photo to prevent memory leak
        if self.current_photo:
            self.photo_label.configure(image='')
            self.current_photo = None
            
        # Show new photo
        from PIL import ImageTk
        photo = ImageTk.PhotoImage(combined_image)
        self.photo_label.configure(image=photo)
        self.photo_label.image = photo  # Keep reference
        self.current_photo = photo  # Track for cleanup
        self.photo_label.pack(fill=tk.BOTH, expand=True)
        
        # Memory management
        self.check_memory_cleanup()
        
        # Schedule next media
        delay = self.photo_delay if hasattr(self, 'photo_delay') else config.MEDIA['photo_delay']
        self._scheduled_after = self.root.after(delay, self.show_next_media)
    
    def show_video(self, video_path):
        """Play a video"""
        # Hide photo label
        self.photo_label.pack_forget()
        
        # Show video player
        self.video_player.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Play video with callback for next media
        self.video_player.play_video(video_path, on_complete=self.show_next_media)
    
    def quit(self):
        """Clean shutdown"""
        # Clean up photos
        if self.current_photo:
            self.photo_label.configure(image='')
            self.current_photo = None
        
        # Clean up image cache
        self.cleanup_image_cache()
        
        # Clean up video player
        if self.video_player:
            self.video_player.cleanup()
        
        # Force garbage collection
        gc.collect()
        
        self.root.quit()
    
    def cleanup_image_cache(self):
        """Clean up cached combined images"""
        if hasattr(self, 'image_cache'):
            for img in self.image_cache:
                if img and hasattr(img, 'close'):
                    img.close()
            self.image_cache.clear()
    
    def manage_cache_size(self):
        """Limit the size of cached images"""
        if len(self.combined_images) > self.max_cache_size:
            # Keep only the most recent images
            old_images = self.combined_images[:-self.max_cache_size]
            for img in old_images:
                if img and hasattr(img, 'close'):
                    img.close()
            self.combined_images = self.combined_images[-self.max_cache_size:]
    
    def check_memory_cleanup(self):
        """Periodically force garbage collection"""
        current_time = time.time()
        gc_interval = config.MEMORY_MANAGEMENT.get('force_gc_interval', 3600)
        
        if current_time - self.last_gc_time > gc_interval:
            gc.collect()
            self.last_gc_time = current_time
            if config.DEBUG.get('verbose_logging', False):
                logging.info(f"Garbage collection performed at {current_time}")
    
    def refresh_media(self):
        """Refresh media lists (for detecting new files)"""
        new_images = get_image_files(self.media_dir)
        self.all_image_files = new_images  # Update reference
        new_videos = self.get_video_files()
        
        if len(new_images) != len(self.all_image_files) or len(new_videos) != len(self.video_files):
            logging.info("Media files changed, refreshing...")
            self.all_image_files = new_images
            self.video_files = new_videos
            
            # Reset batch processing
            self.current_batch_index = 0
            self.cleanup_image_cache()
            self.combined_images = []
            
            # Process first batch of new files
            if self.all_image_files:
                self.process_next_batch()
            
            self.create_media_queue()
        
        # Clean up old cache periodically
        cache_ttl = config.MEMORY_MANAGEMENT.get('image_cache_ttl', 600)
        if time.time() - self.last_gc_time > cache_ttl:
            self.cleanup_image_cache()
            gc.collect()
            self.last_gc_time = time.time()
        
        # Check again based on config
        self.root.after(config.MEDIA['refresh_interval'], self.refresh_media)
    
    def on_volume_up(self, event=None):
        """Handle volume up key press - go to next media"""
        current_time = time.time()
        if current_time - self.last_key_time < config.SYSTEM['key_debounce_time']:
            return  # Ignore rapid key presses
        
        self.last_key_time = current_time
        logging.debug("Volume Up: Next media")
        self.navigate_next()
    
    def on_volume_down(self, event=None):
        """Handle volume down key press - go to previous media"""
        current_time = time.time()
        if current_time - self.last_key_time < config.SYSTEM['key_debounce_time']:
            return  # Ignore rapid key presses
        
        self.last_key_time = current_time
        logging.debug("Volume Down: Previous media")
        self.navigate_previous()
    
    def navigate_next(self):
        """Navigate to next media item"""
        # Cancel any scheduled auto-advance timer
        if self._scheduled_after is not None:
            self.root.after_cancel(self._scheduled_after)
            self._scheduled_after = None

        # Advance to next item and let auto-playing continue
        self.current_index += 1
        self.show_next_media()
    
    def navigate_previous(self):
        """Navigate to previous media item"""
        # Cancel any scheduled auto-advance timer
        if self._scheduled_after is not None:
            self.root.after_cancel(self._scheduled_after)
            self._scheduled_after = None

        # Ensure we have a valid media queue
        if not self.media_queue:
            logging.warning("Warning: Empty media queue, recreating...")
            self.create_media_queue()
            if not self.media_queue:
                logging.error("Error: Still no media available")
                return

        # Go to previous item (wrap around if needed)
        self.current_index = (self.current_index - 1) % len(self.media_queue)

        # Show the previous item and let auto-playing continue
        self.show_next_media()
    


def main():
    parser = argparse.ArgumentParser(description='Mixed Photo/Video Frame for Raspberry Pi')
    parser.add_argument('media_dir', nargs='?', help='Directory containing photos and videos')
    parser.add_argument('--width', type=int, default=None, help='Screen width')
    parser.add_argument('--height', type=int, default=None, help='Screen height')
    parser.add_argument('--delay', type=int, default=None, help='Photo display time in ms')
    parser.add_argument('--config', type=str, help='Path to custom config file')

    args = parser.parse_args()

    # Load custom config FIRST if specified
    if args.config:
        config.load_custom_config(args.config)
    
    # Configure logging
    handlers = []
    if config.LOGGING.get('log_to_console', True):
        handlers.append(logging.StreamHandler())
    if config.LOGGING.get('log_to_file', False):
        log_dir = config.LOGGING.get("log_directory", ".")
        os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(f'{log_dir}/media_frame.log'))
    
    logging.basicConfig(
        level=getattr(logging, config.LOGGING.get('log_level', 'INFO')),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers or [logging.StreamHandler()]  # Fallback to console if no handlers
    )

    # Now set defaults from loaded config
    screen_width = args.width or config.DISPLAY['screen_width']
    screen_height = args.height or config.DISPLAY['screen_height']
    photo_delay = args.delay or config.MEDIA['photo_delay']
    media_dir = args.media_dir or config.get_media_directory()
    
    if not os.path.exists(media_dir):
        logging.error(f"Error: Directory {media_dir} does not exist")
        sys.exit(1)
    
    # Create Tk root
    root = tk.Tk()
    root.title("Media Frame")
    
    # Create and run media frame
    app = MediaFrame(
        root,
        media_dir,
        photo_delay=photo_delay,
        screen_width=screen_width,
        screen_height=screen_height
    )
    
    # Start refresh timer
    app.refresh_media()
    
    # Run main loop
    root.mainloop()


if __name__ == "__main__":
    main()