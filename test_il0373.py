"""
Simple IL0373 Display Test
Tests if display works with IL0373 driver (older e-ink displays)
"""

import time
import board
import displayio
from fourwire import FourWire
import adafruit_il0373

displayio.release_displays()

# Feather pinout for e-ink display
spi = board.SPI()  # Uses SCK and MOSI
epd_cs = board.D9
epd_dc = board.D10
epd_reset = None
epd_busy = None

print("Initializing display bus...")
display_bus = FourWire(spi, command=epd_dc, chip_select=epd_cs, reset=epd_reset, baudrate=1000000)
time.sleep(1)

print("Initializing IL0373 display (296x128, rotation=180)...")
display = adafruit_il0373.IL0373(
    display_bus, width=296, height=128, rotation=180, busy_pin=epd_busy
)

print(f"Display ready: {display.width}x{display.height}")

# Create display group
g = displayio.Group()

# Try to load display-ruler.bmp from root
try:
    print("Loading /display-ruler.bmp...")
    pic = displayio.OnDiskBitmap("/display-ruler.bmp")
    t = displayio.TileGrid(pic, pixel_shader=pic.pixel_shader)
    g.append(t)
    print("Image loaded successfully")
except Exception as e:
    print(f"Error loading image: {e}")
    print("Creating white screen instead...")
    # Create white background as fallback
    bitmap = displayio.Bitmap(display.width, display.height, 1)
    palette = displayio.Palette(1)
    palette[0] = 0xFFFFFF
    bg = displayio.TileGrid(bitmap, pixel_shader=palette)
    g.append(bg)

# Place the display group on the screen
print("Setting display.root_group...")
display.root_group = g

# Refresh the display to have it actually show the image
# NOTE: Do not refresh eInk displays sooner than 180 seconds
print("Refreshing display (this takes a few seconds)...")
display.refresh()
print("Display refreshed!")

print("\nWaiting 180 seconds before allowing next refresh...")
time.sleep(180)
print("Ready for next refresh")
