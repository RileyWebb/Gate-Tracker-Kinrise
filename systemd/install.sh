#!/bin/bash
# Script to install and enable the systemd service and timer

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (e.g., sudo ./install.sh)"
  exit 1
fi

# Get the absolute path of the directory this script is in
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SERVICE_NAME="gate-tracker-pull"

echo "Making the pull script executable..."
chmod +x "$SCRIPT_DIR/pull-repo.sh"

echo "Important: Please make sure you have edited pull-repo.sh and gate-tracker-pull.service to match the ABSOLUTE paths on this machine."
echo "Currently paths default to /opt/Gate-Tracker-Kinrise"

# Copy systemd files to the system directory.
# We modify ExecStart in the service file to use the correct absolute path mathematically if it's left default,
# but it is usually easier to just copy them.
cp "$SCRIPT_DIR/$SERVICE_NAME.service" /etc/systemd/system/
cp "$SCRIPT_DIR/$SERVICE_NAME.timer" /etc/systemd/system/

# Update the service file with the correct path dynamically
sed -i "s|ExecStart=.*|ExecStart=$SCRIPT_DIR/pull-repo.sh|g" /etc/systemd/system/$SERVICE_NAME.service

# Reload systemd to recognize the new files
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable and start the timer (not the service directly, the timer triggers the service)
echo "Enabling and starting the $SERVICE_NAME timer..."
systemctl enable "$SERVICE_NAME.timer"
systemctl start "$SERVICE_NAME.timer"

echo "------------------------------------------------------"
echo "Installation complete!"
echo "You can check the timer status with:"
echo "  systemctl status $SERVICE_NAME.timer"
echo "You can view the logs of the pull script with:"
echo "  journalctl -u $SERVICE_NAME.service -f"
