# File: slideshow_lib.py

import os
import math
from PIL import ExifTags, Image, ImageTk, ImageOps
import tkinter as tk
import config
import gc

class Slideshow:
    def __init__(self, root, combined_images, delay, screen_width, screen_height):
        self.root = root
        self.combined_images = combined_images
        self.delay = delay
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.index = 0
        self.current_photo = None  # Track current photo for cleanup

        self.label = tk.Label(root)
        self.label.pack()

        self.update_image()

    def update_image(self):
        if self.index < len(self.combined_images):
            # Clean up previous photo
            if self.current_photo:
                self.label.config(image='')
                self.current_photo = None
            
            image = self.combined_images[self.index]
            photo = ImageTk.PhotoImage(image)
            self.label.config(image=photo)
            self.label.image = photo
            self.current_photo = photo  # Track for cleanup

            self.index += 1
            
            # Periodic garbage collection
            if self.index % 10 == 0:
                gc.collect()
            
            self.root.after(self.delay, self.update_image)
        else:
            # Clean up before quit
            self.cleanup()
            # Schedule the next batch of images (if any)
            self.root.after(0, self.root.quit)
    
    def reset(self, combined_images):
        # Clean up old images
        if self.current_photo:
            self.label.config(image='')
            self.current_photo = None
        
        self.combined_images = combined_images
        self.index = 0
        gc.collect()  # Force garbage collection on reset
        self.update_image()
    
    def cleanup(self):
        """Clean up resources"""
        if self.current_photo:
            self.label.config(image='')
            self.current_photo = None
        gc.collect()

def get_image_files(directory):
    supported_formats = config.MEDIA['supported_image_formats']
    all_files = [os.path.join(directory, f) for f in os.listdir(directory) if (f.lower().endswith(supported_formats) and not f.lower().startswith("."))]
    return all_files

def correct_orientation(image):
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        exif = image._getexif()
        if exif is not None:
            orientation_value = exif.get(orientation)
            if orientation_value == 3:
                image = image.rotate(180, expand=True)
            elif orientation_value == 6:
                image = image.rotate(270, expand=True)
            elif orientation_value == 8:
                image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        pass
    return image

def create_combined_images(image_files, screen_width, screen_height, border_size=None):
    if border_size is None:
        border_size = config.SLIDESHOW['border_size']
    
    combined_images = []
    current_image_row = []
    current_width = 0
    border_height = config.SLIDESHOW['border_height']
    adaptive_top_height = config.SLIDESHOW['adaptive_top_height']
    
    for image_file in image_files:
        img = Image.open(image_file)
        img = correct_orientation(img)
        img_width, img_height = img.size
        
        # Rescale image based on screen height minus border height
        scaled_height = screen_height - 2 * border_height
        scaled_width = int(img_width * scaled_height / img_height)
        scaled_img = img.resize((scaled_width, scaled_height), Image.ANTIALIAS)
        
        if current_width + scaled_width + (len(current_image_row) * border_size) <= screen_width:
            current_image_row.append(scaled_img)
            current_width += scaled_width + border_size
        else:
            # Remove last border size
            current_width -= border_size
            combined_images.append((current_image_row, current_width))
            current_image_row = [scaled_img]
            current_width = scaled_width + border_size
    
    # Append the last row
    if current_image_row:
        # Remove last border size
        current_width -= border_size
        combined_images.append((current_image_row, current_width))
    
    final_images = []
    for row_images, row_width in combined_images:
        # Calculate even borders for width
        total_image_width = sum(img.width for img in row_images)
        num_gaps = len(row_images) + 1
        even_border_width = (screen_width - total_image_width) // num_gaps
        
        combined_img = Image.new('RGB', (screen_width, screen_height), (255, 255, 255))
        x_offset = even_border_width
        
        for img in row_images:
            combined_img.paste(img, (x_offset, adaptive_top_height))
            x_offset += img.width + even_border_width
        
        final_images.append(combined_img)
    
    return final_images