# File: main.py

import os
import tkinter as tk
from slideshow_lib import Slideshow, get_image_files, create_combined_images
import config
import argparse

def main():
    parser = argparse.ArgumentParser(description='Photo slideshow application')
    parser.add_argument('image_dir', nargs='?', help='Directory containing images')
    parser.add_argument('--delay', type=int, help='Photo display time in milliseconds')
    parser.add_argument('--batch', type=int, help='Number of images per batch')
    parser.add_argument('--width', type=int, help='Screen width')
    parser.add_argument('--height', type=int, help='Screen height')
    parser.add_argument('--config', type=str, help='Path to custom config file')
    
    args = parser.parse_args()
    
    # Load custom config if specified
    if args.config:
        config.load_custom_config(args.config)
    
    # Use arguments or config defaults
    image_directory = args.image_dir or config.get_media_directory()
    delay = args.delay or config.MEDIA['photo_delay']
    batch_size = args.batch or config.SLIDESHOW['batch_size']

    if os.environ.get('DISPLAY', '') == '':
        print('No display found. Using a virtual display.')
        os.environ['DISPLAY'] = config.SYSTEM['virtual_display']
    
    root = tk.Tk()
    root.title("Photo Slideshow")
    
    # Set fullscreen from config
    if config.DISPLAY['fullscreen']:
        root.attributes('-fullscreen', True)
    
    # Hide cursor if configured
    if config.DISPLAY['hide_cursor']:
        root.config(cursor="none")
    
    # Set background color
    root.configure(bg=config.DISPLAY['background_color'])
    
    # Screen dimensions from args or config
    screen_width = args.width if hasattr(args, 'width') and args.width else config.DISPLAY['screen_width']
    screen_height = args.height if hasattr(args, 'height') and args.height else config.DISPLAY['screen_height']
    
    slideshow = None
    
    while True:
        # Put this in the for-loop to update images files
        image_files = get_image_files(image_directory)
        if not image_files:
            print(f"No images found in {image_directory}")
            break
            
        for i in range(0, len(image_files), batch_size):
            image_batch = image_files[i:i+batch_size]
            combined_images = create_combined_images(image_batch, screen_width, screen_height)
            if not combined_images:
                print("No images found in the batch.")
                continue
            if slideshow is None:
                slideshow = Slideshow(root, combined_images, delay, screen_width, screen_height)
            else:
                slideshow.reset(combined_images)
            root.mainloop()

if __name__ == "__main__":
    main()
