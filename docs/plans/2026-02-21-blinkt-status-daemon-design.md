# Blinkt Status Daemon — Design

## Purpose

A lightweight systemd service that runs on all 3 Raspberry Pi 5s, showing WiFi connectivity and CPU usage on the Blinkt! LED strip. When the cable-tester experiment starts, it stops this daemon and takes over all 8 LEDs.

## LED Layout

```
[0]     [1] [2] [3] [4] [5] [6] [7]
WiFi     |------- CPU usage -------|
         green → yellow →   red
```

### LED 0 — WiFi Status

- **White**: WiFi associated to AP (Pi #1, Pi #2) or AP is active/broadcasting (Pi #3)
- **Red**: disconnected / AP down
- Poll interval: 2 seconds

Detection method:
- Pi #1 / Pi #2: check `iw dev wlan0 link` for association state
- Pi #3: check `hostapd` is running via systemd

### LEDs 1-7 — CPU Usage (gradient bar)

- Number of lit LEDs = `round(cpu_percent / 100 * 7)`
- Gradient colors (fixed positions):
  - LEDs 1-2: green (0, 255, 0)
  - LEDs 3-4: yellow (255, 255, 0)
  - LEDs 5-6: orange (255, 100, 0)
  - LED 7: red (255, 0, 0)
- Only lit up to the current CPU level; rest are off
- Poll interval: 2 seconds
- CPU measured via `psutil.cpu_percent(interval=None)` with polling loop

### Brightness

Global brightness: 0.05 (dim, consistent with cable-tester's 0.1 but lower for always-on status)

## Takeover Protocol

The cable-tester experiment needs all 8 LEDs. Integration:

1. Cable-tester `install.sh` or `run.py` calls `sudo systemctl stop blinkt-status` before starting
2. Cable-tester owns all 8 LEDs for experiment duration
3. Cable-tester calls `sudo systemctl start blinkt-status` on shutdown/completion

No IPC or socket needed — just systemd start/stop.

## Architecture

### Single script: `blinkt_status.py`

- Uses patched `blinkt.py` (lgpio for Pi 5)
- Uses `psutil` for CPU measurement
- Detects role automatically:
  - If `hostapd` service exists and is enabled → router mode (check AP active)
  - Otherwise → client mode (check WiFi association)
- Main loop: every 2 seconds, update LED 0 (WiFi) and LEDs 1-7 (CPU)
- Handles SIGTERM gracefully: clears LEDs and exits

### systemd service: `blinkt-status.service`

- Runs as root (GPIO access)
- `Type=simple`
- `Restart=on-failure`
- `ExecStop` triggers clean LED shutdown via SIGTERM

### Install script: `install.sh`

- Installs `psutil` if missing
- Copies service file to `/etc/systemd/system/`
- Enables and starts the service
- Idempotent (safe to re-run)

## Dependencies

- Python 3
- `blinkt` (patched for Pi 5, already installed on Pi #1)
- `psutil` (pip install)
- `lgpio` (already available on Pi 5)

## Deployment

Identical script on all 3 Pis. Role detection is automatic. Install via:

```bash
sudo ./install.sh
```

## File Structure

```
blinkt-status/
├── blinkt_status.py      # Main daemon script
├── install.sh            # Setup + systemd registration
└── docs/plans/
    └── 2026-02-21-blinkt-status-daemon-design.md
```
