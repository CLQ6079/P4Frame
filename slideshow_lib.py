# File: slideshow_lib.py

import os
import math
from PIL import ExifTags, Image, ImageTk, ImageOps, ImageDraw, ImageFont
import tkinter as tk
import config
import gc
from datetime import datetime

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

def get_photo_timestamp(image):
    """Extract timestamp from photo EXIF metadata"""
    try:
        exif = image._getexif()
        if exif is not None:
            # Try different timestamp fields in order of preference
            timestamp_tags = ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized']
            
            for tag_name in timestamp_tags:
                for tag_id in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[tag_id] == tag_name:
                        timestamp_str = exif.get(tag_id)
                        if timestamp_str:
                            try:
                                # Parse EXIF datetime format: "YYYY:MM:DD HH:MM:SS"
                                dt = datetime.strptime(timestamp_str, "%Y:%m:%d %H:%M:%S")
                                return dt.strftime("%Y-%m-%d %H:%M:%S")
                            except ValueError:
                                continue
    except (AttributeError, KeyError, TypeError):
        pass
    return None

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

def add_timestamp_overlay(image, timestamp):
    """Add timestamp overlay to bottom-right corner of image"""
    try:
        # Create a copy to avoid modifying original
        img_with_timestamp = image.copy()
        draw = ImageDraw.Draw(img_with_timestamp)
        
        # Try to use a system font, fallback to default
        try:
            # Adjust font size based on image height
            font_size = max(20, min(40, image.height // 25))
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size)
        except (IOError, OSError):
            try:
                font = ImageFont.truetype("arial.ttf", 24)
            except (IOError, OSError):
                font = ImageFont.load_default()
        
        # Get text dimensions
        bbox = draw.textbbox((0, 0), timestamp, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Position in bottom-right corner with padding
        padding = 10
        x = image.width - text_width - padding
        y = image.height - text_height - padding
        
        # Add semi-transparent background for better readability
        bg_padding = 5
        bg_coords = [
            x - bg_padding,
            y - bg_padding,
            x + text_width + bg_padding,
            y + text_height + bg_padding
        ]
        draw.rectangle(bg_coords, fill=(255, 255, 255, 180))
        
        # Draw black text
        draw.text((x, y), timestamp, fill=(0, 0, 0), font=font)
        
        return img_with_timestamp
    except Exception as e:
        # If overlay fails, return original image
        print(f"Warning: Could not add timestamp overlay: {e}")
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
        
        # Extract timestamp before any processing
        timestamp = get_photo_timestamp(img)
        
        img = correct_orientation(img)
        img_width, img_height = img.size
        
        # Rescale image based on screen height minus border height
        scaled_height = screen_height - 2 * border_height
        scaled_width = int(img_width * scaled_height / img_height)
        scaled_img = img.resize((scaled_width, scaled_height), Image.LANCZOS)
        
        # Add timestamp overlay if available and enabled
        if timestamp and config.SLIDESHOW.get('show_timestamps', True):
            scaled_img = add_timestamp_overlay(scaled_img, timestamp)
        
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