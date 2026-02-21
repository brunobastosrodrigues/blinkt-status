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
