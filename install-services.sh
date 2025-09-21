#!/bin/bash
# Installation script for P4Frame services

set -e

# Ensure script is executable
chmod +x "$0"

# Fix potential Windows line endings
dos2unix "$0" 2>/dev/null || true

# Set proper environment for systemd/dbus operations
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"

# Ensure we're in the correct directory
cd "$(dirname "$0")"

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

# Create all directories needed by the services
mkdir -p /home/pi/P4Frame/logs/video_converter
mkdir -p /share/study/lgy_photoframe/data

# Install log rotation
if [ "$EUID" -eq 0 ]; then
    if [ -f "logrotate.conf" ]; then
        echo "Installing log rotation configuration..."
        cp logrotate.conf /etc/logrotate.d/p4frame
        chmod 644 /etc/logrotate.d/p4frame
        echo "Log rotation installed"
    else
        echo "Warning: logrotate.conf not found, skipping log rotation setup"
    fi
fi

# Install systemd services
echo "Installing systemd services..."

# Install video converter service (system service)
if [ "$EUID" -eq 0 ]; then
    if [ -f "video-converter.service" ]; then
        cp video-converter.service /etc/systemd/system/
        systemctl daemon-reload
        systemctl enable video-converter.service
        echo "Video converter service installed and enabled"
    else
        echo "Warning: video-converter.service not found, skipping"
    fi
else
    echo "Skipping system service installation (requires sudo)"
fi

# Install main P4Frame service (system service for proper display access)
if [ "$EUID" -eq 0 ]; then
    # Set up directories and permissions
    echo "Setting up P4Frame directories and permissions..."
    chown -R pi:pi /home/pi/P4Frame
    chmod +x /home/pi/P4Frame/media_frame.py

    # Set permissions for all service directories
    echo "Setting directory permissions..."
    chown -R pi:pi /home/pi/P4Frame/logs
    chown -R pi:pi /share/study/lgy_photoframe/data
    chmod -R 755 /share/study/lgy_photoframe/data

    # Install as system service for proper display access
    if [ -f "p4frame.service" ]; then
        cp p4frame.service /etc/systemd/system/
        systemctl daemon-reload
        systemctl enable p4frame.service
        echo "P4Frame system service installed and enabled"
    else
        echo "Error: p4frame.service not found!"
        exit 1
    fi
else
    echo "P4Frame requires system service installation (run with sudo)"
fi

# Install cron job for weekly restart
echo ""
if [ -f "install-cron.sh" ] && [ -f "cron-restart.sh" ]; then
    echo "Installing weekly restart cron job..."
    chmod +x cron-restart.sh
    chmod +x install-cron.sh
    ./install-cron.sh
else
    echo "Warning: cron scripts not found, skipping cron job installation"
fi

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
echo "Verifying installation..."
if [ "$EUID" -eq 0 ]; then
    if systemctl is-enabled p4frame.service >/dev/null 2>&1; then
        echo "✓ P4Frame service is enabled"
    else
        echo "✗ P4Frame service installation may have failed"
    fi
    if systemctl is-enabled video-converter.service >/dev/null 2>&1; then
        echo "✓ Video converter service is enabled"
    else
        echo "⚠ Video converter service not enabled (may be normal if file not found)"
    fi
fi
echo ""
echo "To start services now:"
echo "  sudo systemctl start video-converter.service"
echo "  sudo systemctl start p4frame.service"
echo ""
echo "To check service status:"
echo "  sudo systemctl status video-converter.service"
echo "  sudo systemctl status p4frame.service"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u video-converter.service -f"
echo "  sudo journalctl -u p4frame.service -f"
echo ""
echo "Services will start automatically on boot."