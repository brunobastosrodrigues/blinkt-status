#!/bin/bash
# Install blinkt-status daemon on a Raspberry Pi 5.
# Usage: sudo ./install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="blinkt-status"
INSTALL_DIR="/opt/blinkt-status"

if [[ $EUID -ne 0 ]]; then
    echo "Error: run with sudo"
    exit 1
fi

echo "=== Installing blinkt-status daemon ==="

# Install psutil if missing
python3 -c "import psutil" 2>/dev/null || {
    echo "Installing psutil..."
    apt-get install -y python3-psutil
}

# Install patched blinkt library if missing
python3 -c "import blinkt" 2>/dev/null || {
    echo "Installing patched blinkt.py for Pi 5..."
    cp "$SCRIPT_DIR/blinkt_pi5.py" /usr/lib/python3/dist-packages/blinkt.py
    echo "Installed blinkt.py"
}

# Copy daemon script
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/blinkt_status.py" "$INSTALL_DIR/blinkt_status.py"

# Create systemd service
cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Blinkt Status Daemon (WiFi + CPU)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/blinkt_status.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo "=== blinkt-status installed and running ==="
echo "Check status: systemctl status $SERVICE_NAME"
echo "Stop (for cable-tester): sudo systemctl stop $SERVICE_NAME"
echo "Start again: sudo systemctl start $SERVICE_NAME"
