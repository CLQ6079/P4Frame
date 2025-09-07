#!/bin/bash
# Installation script for P4Frame services

set -e

echo "=== P4Frame Service Installation ==="
echo ""

# Check if running as root for system service installation
if [ "$EUID" -ne 0 ]; then 
   echo "Note: Run as sudo for system-wide installation"
fi

# Create necessary directories
echo "Creating directories..."
mkdir -p /home/pi/logs
mkdir -p /home/pi/Pictures/converted

# Install log rotation
if [ "$EUID" -eq 0 ]; then
    echo "Installing log rotation configuration..."
    cp logrotate.conf /etc/logrotate.d/p4frame
    chmod 644 /etc/logrotate.d/p4frame
    echo "Log rotation installed"
fi

# Install systemd services
echo "Installing systemd services..."

# Install video converter service (system service)
if [ "$EUID" -eq 0 ]; then
    cp video-converter.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable video-converter.service
    echo "Video converter service installed and enabled"
else
    echo "Skipping system service installation (requires sudo)"
fi

# Install main P4Frame service (user service)
mkdir -p ~/.config/systemd/user/
cp p4frame.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable p4frame.service
echo "P4Frame user service installed and enabled"

# Install cron job for weekly restart
echo ""
echo "Installing weekly restart cron job..."
chmod +x cron-restart.sh
chmod +x install-cron.sh
./install-cron.sh

# Set up swap if not already configured
if [ "$EUID" -eq 0 ]; then
    if ! swapon --show | grep -q swap; then
        echo ""
        echo "Setting up 2GB swap file..."
        fallocate -l 2G /swapfile
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
        echo "Swap file created and enabled"
    else
        echo "Swap already configured"
    fi
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "To start services now:"
echo "  sudo systemctl start video-converter.service"
echo "  systemctl --user start p4frame.service"
echo ""
echo "To check service status:"
echo "  sudo systemctl status video-converter.service"
echo "  systemctl --user status p4frame.service"
echo ""
echo "To view logs:"
echo "  journalctl -u video-converter.service -f"
echo "  journalctl --user -u p4frame.service -f"
echo ""
echo "Services will start automatically on boot."