#!/usr/bin/env python3
# File: video_converter.py
# Standalone script for background video conversion

import os
import sys
import time
import subprocess
from pathlib import Path
import logging
from datetime import datetime
import config

# Setup logging
if config.LOGGING['enabled']:
    LOG_DIR = config.get_log_directory()
    
    handlers = []
    if config.LOGGING['log_to_file']:
        handlers.append(logging.FileHandler(f'{LOG_DIR}/converter_{datetime.now().strftime("%Y%m%d")}.log'))
    if config.LOGGING['log_to_console']:
        handlers.append(logging.StreamHandler())
    
    logging.basicConfig(
        level=getattr(logging, config.LOGGING['log_level']),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
else:
    logging.basicConfig(level=logging.CRITICAL)

class VideoConverterService:
    def __init__(self, watch_dir=None, check_interval=None, cpu_cores=None):
        self.watch_dir = watch_dir or config.get_media_directory()
        self.converted_dir = os.path.join(self.watch_dir, config.VIDEO_CONVERSION['converted_subfolder'])
        self.check_interval = check_interval or config.VIDEO_CONVERSION['check_interval']
        self.cpu_cores = cpu_cores or config.VIDEO_CONVERSION['cpu_cores']
        self.video_extensions = config.MEDIA['supported_video_formats']
        
        os.makedirs(self.converted_dir, exist_ok=True)
        
    def find_unconverted_videos(self):
        """Find videos that need conversion"""
        unconverted = []
        
        try:
            for file in os.listdir(self.watch_dir):
                if file.lower().endswith(self.video_extensions) and not file.startswith('.'):
                    file_path = os.path.join(self.watch_dir, file)
                    
                    # Skip if it's in the converted directory
                    if 'converted' in file_path:
                        continue
                    
                    # Check if already converted
                    converted_path = os.path.join(self.converted_dir, f"{Path(file).stem}_h264.mp4")
                    if not os.path.exists(converted_path):
                        unconverted.append(file_path)
                        
        except Exception as e:
            logging.error(f"Error scanning directory: {e}")
            
        return unconverted
    
    def check_ffmpeg(self):
        """Check if ffmpeg is installed"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logging.error("FFmpeg not found. Please install: sudo apt-get install ffmpeg")
            return False
    
    def convert_video(self, input_path):
        """Convert a single video to H.264"""
        filename = Path(input_path).stem
        output_path = os.path.join(self.converted_dir, f"{filename}_h264.mp4")
        temp_path = output_path + '.tmp'
        
        # FFmpeg command from configuration
        command = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', config.VIDEO_CONVERSION['codec'],
            '-preset', config.VIDEO_CONVERSION['preset'],
            '-crf', str(config.VIDEO_CONVERSION['crf']),
            '-maxrate', config.VIDEO_CONVERSION['max_bitrate'],
            '-bufsize', config.VIDEO_CONVERSION['buffer_size'],
            '-c:a', config.VIDEO_CONVERSION['audio_codec'],
            '-b:a', config.VIDEO_CONVERSION['audio_bitrate'],
            '-threads', str(self.cpu_cores),
            '-movflags', '+faststart',  # Optimize for streaming
            '-y',                   # Overwrite
            temp_path
        ]
        
        try:
            logging.info(f"Starting conversion: {input_path}")
            start_time = time.time()
            
            result = subprocess.run(command, capture_output=True, text=True, timeout=config.VIDEO_CONVERSION['timeout'])
            
            if result.returncode == 0:
                # Rename temp file to final name
                os.rename(temp_path, output_path)
                
                conversion_time = time.time() - start_time
                logging.info(f"Successfully converted in {conversion_time:.1f}s: {input_path}")
                
                # Delete original if configured
                if config.VIDEO_CONVERSION['delete_originals']:
                    try:
                        os.remove(input_path)
                        logging.info(f"Deleted original: {input_path}")
                    except Exception as e:
                        logging.error(f"Could not delete original: {e}")
                
                return True
            else:
                logging.error(f"Conversion failed: {result.stderr}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return False
                
        except subprocess.TimeoutExpired:
            logging.error(f"Conversion timeout ({config.VIDEO_CONVERSION['timeout']} seconds) for: {input_path}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
        except Exception as e:
            logging.error(f"Error converting {input_path}: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
    
    def run_once(self):
        """Run one conversion cycle"""
        videos = self.find_unconverted_videos()
        
        if videos:
            logging.info(f"Found {len(videos)} videos to convert")
            for video in videos:
                self.convert_video(video)
        
        return len(videos)
    
    def run_service(self):
        """Run as continuous service"""
        logging.info(f"Video converter service started")
        logging.info(f"Watching directory: {self.watch_dir}")
        logging.info(f"Check interval: {self.check_interval} seconds")
        logging.info(f"CPU cores: {self.cpu_cores}")
        
        if not self.check_ffmpeg():
            sys.exit(1)
        
        while True:
            try:
                converted_count = self.run_once()
                if converted_count > 0:
                    logging.info(f"Conversion cycle complete. Processed {converted_count} videos")
                
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logging.info("Service stopped by user")
                break
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                time.sleep(self.check_interval)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Video converter service for H.264 conversion')
    parser.add_argument('watch_dir', nargs='?', help='Directory to watch for videos')
    parser.add_argument('--interval', type=int, help='Check interval in seconds')
    parser.add_argument('--cores', type=int, help='Number of CPU cores to use')
    parser.add_argument('--config', type=str, help='Path to custom config file')
    
    args = parser.parse_args()
    
    # Load custom config if specified
    if args.config:
        config.load_custom_config(args.config)
    
    # Create and run service
    service = VideoConverterService(
        watch_dir=args.watch_dir,
        check_interval=args.interval,
        cpu_cores=args.cores
    )
    
    service.run_service()