# Blinkt Status Daemon Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a systemd service that shows WiFi status (LED 0) and CPU usage gradient (LEDs 1-7) on the Blinkt! strip across all 3 Raspberry Pi 5s.

**Architecture:** Single Python script (`blinkt_status.py`) with a 2-second poll loop. Auto-detects whether it's a router (checks AP active) or client (checks WiFi association). Installed via `install.sh` which copies the patched blinkt.py library if missing, creates a systemd service, and enables it.

**Tech Stack:** Python 3, lgpio, blinkt (Pi 5 patched), psutil

---

### Task 1: Write the main daemon script with WiFi detection

**Files:**
- Create: `blinkt_status.py`

**Step 1: Write the WiFi status detection**

```python
#!/usr/bin/env python3
"""Blinkt status daemon — WiFi connectivity + CPU usage on 8 LEDs."""

import signal
import subprocess
import sys
import time

import blinkt
import psutil

BRIGHTNESS = 0.05
POLL_INTERVAL = 2

# Gradient colors for CPU bar (LEDs 1-7)
CPU_COLORS = [
    (0, 255, 0),     # LED 1: green
    (0, 255, 0),     # LED 2: green
    (255, 255, 0),   # LED 3: yellow
    (255, 255, 0),   # LED 4: yellow
    (255, 100, 0),   # LED 5: orange
    (255, 100, 0),   # LED 6: orange
    (255, 0, 0),     # LED 7: red
]

_running = True


def _signal_handler(sig, frame):
    global _running
    _running = False


def is_router():
    """Check if this Pi is the router (hostapd service exists and is enabled)."""
    try:
        result = subprocess.run(
            ['systemctl', 'is-enabled', 'hostapd'],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() == 'enabled'
    except Exception:
        return False


def wifi_connected():
    """Check if wlan0 is associated to an AP (client mode)."""
    try:
        result = subprocess.run(
            ['iw', 'dev', 'wlan0', 'link'],
            capture_output=True, text=True, timeout=5
        )
        return 'Connected to' in result.stdout
    except Exception:
        return False


def ap_active():
    """Check if hostapd is running (router mode)."""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'hostapd'],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() == 'active'
    except Exception:
        return False


def update_leds(check_fn):
    """Update all LEDs: WiFi status (LED 0) + CPU bar (LEDs 1-7)."""
    blinkt.clear()

    # LED 0: WiFi status
    if check_fn():
        blinkt.set_pixel(0, 255, 255, 255, BRIGHTNESS)  # white = connected
    else:
        blinkt.set_pixel(0, 255, 0, 0, BRIGHTNESS)      # red = disconnected

    # LEDs 1-7: CPU usage gradient
    cpu = psutil.cpu_percent(interval=None)
    lit_count = round(cpu / 100.0 * 7)

    for i in range(7):
        if i < lit_count:
            r, g, b = CPU_COLORS[i]
            blinkt.set_pixel(i + 1, r, g, b, BRIGHTNESS)

    blinkt.show()


def main():
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    blinkt.set_clear_on_exit(True)

    # Determine role
    router = is_router()
    check_fn = ap_active if router else wifi_connected

    role_name = 'router (AP active check)' if router else 'client (WiFi association check)'
    print(f'blinkt-status: starting in {role_name} mode')

    # Prime psutil CPU measurement (first call always returns 0)
    psutil.cpu_percent(interval=None)

    while _running:
        update_leds(check_fn)
        # Sleep in small increments for responsive shutdown
        for _ in range(int(POLL_INTERVAL / 0.1)):
            if not _running:
                break
            time.sleep(0.1)

    blinkt.clear()
    blinkt.show()
    print('blinkt-status: stopped')


if __name__ == '__main__':
    main()
```

**Step 2: Manually test on Pi #1**

Run: `sudo python3 blinkt_status.py`
Expected: LED 0 shows red (WiFi not associated since built-in WiFi is disabled), CPU LEDs light up green-to-red based on current load. Ctrl+C clears LEDs and exits.

**Step 3: Commit**

```bash
git add blinkt_status.py
git commit -m "feat: add blinkt status daemon with WiFi and CPU display"
```

---

### Task 2: Write the install script

**Files:**
- Create: `install.sh`

**Step 1: Write install.sh**

```bash
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
```

**Step 2: Bundle the patched blinkt library**

Copy the patched blinkt.py into the project so install.sh can deploy it to Pis that don't have it:

```bash
cp /usr/lib/python3/dist-packages/blinkt.py blinkt_pi5.py
```

**Step 3: Commit**

```bash
git add install.sh blinkt_pi5.py
git commit -m "feat: add install script and bundled blinkt Pi 5 library"
```

---

### Task 3: Test locally on Pi #1

**Step 1: Run install script**

```bash
cd /home/rodrigues/blinkt-status
sudo ./install.sh
```

Expected: service installs and starts. `systemctl status blinkt-status` shows active.

**Step 2: Verify LED behavior**

- LED 0: red (built-in WiFi disabled in CSI mode)
- LEDs 1-7: CPU gradient visible

**Step 3: Verify clean stop**

```bash
sudo systemctl stop blinkt-status
```

Expected: all LEDs turn off cleanly.

**Step 4: Verify restart**

```bash
sudo systemctl start blinkt-status
```

Expected: LEDs come back.

**Step 5: Commit any fixes**

---

### Task 4: Deploy to Pi #3 (router)

**Step 1: Copy project to Pi #3**

```bash
scp -r /home/rodrigues/blinkt-status rodrigues@192.168.1.89:~/blinkt-status
```

**Step 2: Install on Pi #3**

```bash
sshpass -p 'semsenha' ssh rodrigues@192.168.1.89 \
  'echo "semsenha" | sudo -S bash /home/rodrigues/blinkt-status/install.sh'
```

Expected: psutil already installed, blinkt.py gets copied, service starts.

**Step 3: Verify on Pi #3**

```bash
sshpass -p 'semsenha' ssh rodrigues@192.168.1.89 \
  'sudo systemctl status blinkt-status'
```

Expected: active, running in client mode (hostapd not yet configured).

---

### Task 5: Deploy to Pi #2 (client node)

**Step 1: Copy project to Pi #2**

```bash
scp -r /home/rodrigues/blinkt-status rodrigues@192.168.1.90:~/blinkt-status
```

**Step 2: Install on Pi #2**

```bash
sshpass -p 'semsenha' ssh rodrigues@192.168.1.90 \
  'echo "semsenha" | sudo -S bash /home/rodrigues/blinkt-status/install.sh'
```

**Step 3: Verify on Pi #2**

```bash
sshpass -p 'semsenha' ssh rodrigues@192.168.1.90 \
  'sudo systemctl status blinkt-status'
```

Expected: active, running in client mode. LED 0 white (WiFi associated), CPU bar visible.

---

### Task 6: Integration — update cable-tester to stop/start blinkt-status

**Files:**
- Modify: `/home/rodrigues/cable-tester/server/server_app.py` (add systemctl stop/start calls)
- Modify: `/home/rodrigues/cable-tester/client/client_agent.py` (add systemctl stop/start calls)
- Modify: `/home/rodrigues/cable-tester/install.sh` (add blinkt-status dependency note)

**Step 1: Add helper to cable-tester server**

In `server/server_app.py`, at startup after imports:

```python
import subprocess

def _blinkt_status(action):
    """Start or stop the blinkt-status daemon."""
    try:
        subprocess.run(['sudo', 'systemctl', action, 'blinkt-status'],
                       capture_output=True, timeout=10)
    except Exception:
        pass  # daemon may not be installed
```

Call `_blinkt_status('stop')` at server startup (before `show_role()`).
Call `_blinkt_status('start')` in a shutdown hook / atexit.

**Step 2: Add same helper to cable-tester client**

Same pattern in `client/client_agent.py`.

**Step 3: Test the integration**

Start blinkt-status, then start cable-tester — LEDs should switch from status display to cable-tester animations. When cable-tester stops, status display should resume.

**Step 4: Commit**

```bash
cd /home/rodrigues/cable-tester
git add server/server_app.py client/client_agent.py
git commit -m "feat: stop/start blinkt-status daemon on cable-tester lifecycle"
```
