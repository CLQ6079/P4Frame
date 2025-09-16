#!/bin/bash
#
# CRON RESTART SCRIPT FOR P4FRAME
# Summary: Performs weekly maintenance restart of P4Frame services
# - Gracefully stops P4Frame and video converter services
# - Cleans up temporary files and manages log file sizes
# - Restarts services and maintains restart logs
# - Designed to run weekly via cron (Sunday 3 AM)
#
# Add to crontab with: crontab -e
# Add line: 0 3 * * 0 /home/pi/P4Frame/cron-restart.sh

# Log the restart
echo "$(date): Starting weekly P4Frame restart" >> /home/pi/logs/p4frame-restart.log

# Stop services gracefully
systemctl --user stop p4frame.service 2>/dev/null || true
systemctl stop video-converter.service 2>/dev/null || true

# Wait for processes to fully stop
sleep 5

# Clear any temporary files
rm -f /tmp/p4frame-* 2>/dev/null || true

# Clear systemd journal if it's getting large
if [ $(journalctl --disk-usage | awk '{print $7}' | sed 's/M//') -gt 100 ]; then
    sudo journalctl --vacuum-size=50M
fi

# Start services again
systemctl start video-converter.service 2>/dev/null || true
systemctl --user start p4frame.service 2>/dev/null || true

echo "$(date): P4Frame restart completed" >> /home/pi/logs/p4frame-restart.log

# Keep only last 4 weeks of restart logs
tail -n 100 /home/pi/logs/p4frame-restart.log > /tmp/restart.tmp && mv /tmp/restart.tmp /home/pi/logs/p4frame-restart.log