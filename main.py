# File: main.py

import os
import tkinter as tk
from slideshow_lib import Slideshow, get_image_files, create_combined_images

def main():
    # Configurations for this program
    image_directory = "./data"  # Update this to your directory
    delay = 30000  # milliseconds
    batch_size = 10  # Number of files to process in each batch. This affects how smart this program combines images. But it can be slow when it's a big number.

    if os.environ.get('DISPLAY', '') == '':
        print('No display found. Using a virtual display.')
        os.environ['DISPLAY'] = ':0.0'
    
    root = tk.Tk()
    root.title("Photo Slideshow")
    root.attributes('-fullscreen', True)  # Set the window to fullscreen mode

    screen_width = 2560
    screen_height = 1080
    
    slideshow = None
    
    while True:
        # Put this in the for-loop to update images files
        image_files = get_image_files(image_directory)
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
