import atexit
import glob
import time

import lgpio


__version__ = '0.1.3-pi5'


def _find_rp1_chip():
    """Find the gpiochip number for the RP1 (Pi 5 header GPIOs)."""
    for path in sorted(glob.glob('/sys/bus/gpio/devices/gpiochip*/label')):
        with open(path) as f:
            if 'pinctrl-rp1' in f.read():
                return int(path.split('gpiochip')[1].split('/')[0])
    return 0

DAT = 23
CLK = 24
NUM_PIXELS = 8
BRIGHTNESS = 7

pixels = [[0, 0, 0, BRIGHTNESS]] * NUM_PIXELS

_gpio_setup = False
_clear_on_exit = True
_handle = None

def _exit():
    global _handle
    if _clear_on_exit:
        clear()
        show()
    if _handle is not None:
        lgpio.gpiochip_close(_handle)
        _handle = None

def set_brightness(brightness):
    """Set the brightness of all pixels

    :param brightness: Brightness: 0.0 to 1.0
    """

    if brightness < 0 or brightness > 1:
        raise ValueError("Brightness should be between 0.0 and 1.0")

    for x in range(NUM_PIXELS):
        pixels[x][3] = int(31.0 * brightness) & 0b11111

def clear():
    """Clear the pixel buffer"""
    for x in range(NUM_PIXELS):
        pixels[x][0:3] = [0, 0, 0]

def _write_byte(byte):
    for x in range(8):
        lgpio.gpio_write(_handle, DAT, 1 if byte & 0b10000000 else 0)
        lgpio.gpio_write(_handle, CLK, 1)
        time.sleep(0.0000005)
        byte <<= 1
        lgpio.gpio_write(_handle, CLK, 0)
        time.sleep(0.0000005)

# Emit exactly enough clock pulses to latch the small dark die APA102s which are weird
# for some reason it takes 36 clocks, the other IC takes just 4 (number of pixels/2)
def _eof():
    lgpio.gpio_write(_handle, DAT, 0)
    for x in range(36):
        lgpio.gpio_write(_handle, CLK, 1)
        time.sleep(0.0000005)
        lgpio.gpio_write(_handle, CLK, 0)
        time.sleep(0.0000005)

def _sof():
    lgpio.gpio_write(_handle, DAT, 0)
    for x in range(32):
        lgpio.gpio_write(_handle, CLK, 1)
        time.sleep(0.0000005)
        lgpio.gpio_write(_handle, CLK, 0)
        time.sleep(0.0000005)

def show():
    """Output the buffer to Blinkt!"""
    global _gpio_setup, _handle

    if not _gpio_setup:
        _handle = lgpio.gpiochip_open(_find_rp1_chip())
        try:
            lgpio.gpio_claim_output(_handle, DAT)
        except lgpio.error:
            lgpio.gpio_free(_handle, DAT)
            lgpio.gpio_claim_output(_handle, DAT)
        try:
            lgpio.gpio_claim_output(_handle, CLK)
        except lgpio.error:
            lgpio.gpio_free(_handle, CLK)
            lgpio.gpio_claim_output(_handle, CLK)
        atexit.register(_exit)
        _gpio_setup = True

    _sof()

    for pixel in pixels:
        r, g, b, brightness = pixel
        _write_byte(0b11100000 | brightness)
        _write_byte(b)
        _write_byte(g)
        _write_byte(r)

    _eof()

def set_all(r, g, b, brightness=None):
    """Set the RGB value and optionally brightness of all pixels

    If you don't supply a brightness value, the last value set for each pixel be kept.

    :param r: Amount of red: 0 to 255
    :param g: Amount of green: 0 to 255
    :param b: Amount of blue: 0 to 255
    :param brightness: Brightness: 0.0 to 1.0 (default around 0.2)
    """
    for x in range(NUM_PIXELS):
        set_pixel(x, r, g, b, brightness)

def get_pixel(x):
    """Get the RGB and brightness value of a specific pixel"""

    r, g, b, brightness = pixels[x]
    brightness /= 31.0

    return r, g, b, round(brightness, 3)

def set_pixel(x, r, g, b, brightness=None):
    """Set the RGB value, and optionally brightness, of a single pixel

    If you don't supply a brightness value, the last value will be kept.

    :param x: The horizontal position of the pixel: 0 to 7
    :param r: Amount of red: 0 to 255
    :param g: Amount of green: 0 to 255
    :param b: Amount of blue: 0 to 255
    :param brightness: Brightness: 0.0 to 1.0 (default around 0.2)
    """
    if brightness is None:
        brightness = pixels[x][3]
    else:
        brightness = int(31.0 * brightness) & 0b11111

    pixels[x] = [int(r) & 0xff, int(g) & 0xff, int(b) & 0xff, brightness]

def set_clear_on_exit(value=True):
    """Set whether Blinkt! should be cleared upon exit

    By default Blinkt! will turn off the pixels on exit, but calling::

        blinkt.set_clear_on_exit(False)

    Will ensure that it does not.

    :param value: True or False (default True)
    """
    global _clear_on_exit
    _clear_on_exit = value
