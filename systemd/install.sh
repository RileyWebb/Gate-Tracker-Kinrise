#!/bin/bash
# Script to install and enable the systemd service and timer

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (e.g., sudo ./install.sh)"
  exit 1
fi

# Get the absolute path of the directory this script is in
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
SERVICE_NAME="gate-tracker-pull"

echo "Installing required Python packages for the Server and GPIO Watcher..."
# Using apt-get is the safest method on systems like Raspberry Pi OS to avoid PEP 668 'externally managed environment' errors
apt-get update
apt-get install -y python3-pip python3-flask python3-requests python3-gpiozero

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

echo "Setting up external configuration directory..."
mkdir -p /etc/gate-tracker
if [ ! -f "/etc/gate-tracker/config.json" ]; then
    echo "Copying default config.json to /etc/gate-tracker/..."
    cp "$REPO_DIR/src/config.json" /etc/gate-tracker/config.json
    # Restrict permissions since it contains passwords and tokens
    chmod 600 /etc/gate-tracker/config.json
else
    echo "Configuration file already exists in /etc/gate-tracker. Skipping default copy."
fi

echo "Configuring and enabling the Flask API Server..."
cp "$SCRIPT_DIR/gate-tracker-server.service" /etc/systemd/system/
sed -i "s|WorkingDirectory=.*|WorkingDirectory=$REPO_DIR/src|g" /etc/systemd/system/gate-tracker-server.service
sed -i "s|ExecStart=.*|ExecStart=/usr/bin/python3 $REPO_DIR/src/server.py|g" /etc/systemd/system/gate-tracker-server.service
systemctl enable gate-tracker-server.service
systemctl start gate-tracker-server.service

echo "Configuring and enabling the GPIO Watcher..."
cp "$SCRIPT_DIR/gate-tracker-watcher.service" /etc/systemd/system/
sed -i "s|WorkingDirectory=.*|WorkingDirectory=$REPO_DIR/src|g" /etc/systemd/system/gate-tracker-watcher.service
sed -i "s|ExecStart=.*|ExecStart=/usr/bin/python3 $REPO_DIR/src/gpio_watcher.py|g" /etc/systemd/system/gate-tracker-watcher.service
systemctl enable gate-tracker-watcher.service
systemctl start gate-tracker-watcher.service

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
