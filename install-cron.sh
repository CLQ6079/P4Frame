#!/bin/bash
# Script to install the cron job for weekly restart

echo "Installing P4Frame weekly restart cron job..."

# Make the restart script executable
chmod +x /home/pi/P4Frame/cron-restart.sh

# Create logs directory if it doesn't exist
mkdir -p /home/pi/logs

# Add cron job (weekly restart on Sunday at 3 AM)
(crontab -l 2>/dev/null | grep -v "cron-restart.sh"; echo "0 3 * * 0 /home/pi/P4Frame/cron-restart.sh") | crontab -

echo "Cron job installed. Current crontab:"
crontab -l

echo ""
echo "The service will automatically restart every Sunday at 3 AM."
echo "Logs will be saved to /home/pi/logs/p4frame-restart.log"