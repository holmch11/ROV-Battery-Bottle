"""
Simple E-Ink Display

Modes:
- TEST_PATTERN_ONLY: Show a half-black / half-white test image (one-time refresh)
- Otherwise: BME280 sensor readings for Temperature, Humidity, and Pressure

Hardware:
- Adafruit Feather ESP32-S2
- 2.9" Flexible Monochrome E-Ink Display (Adafruit #4262, UC8151D)
- BME280 sensor on I2C (optional)
"""

import time
import board
import busio
import displayio
from fourwire import FourWire
import adafruit_uc8151d

try:
    import adafruit_bme280.advanced as adafruit_bme280
    _bme_available = True
except ImportError:
    _bme_available = False
    print("BME280 library not found")

displayio.release_displays()

# ===== CONFIG =====
# Set True to display a simple half-black/half-white screen for testing.
# The left half is black, the right half is white.
TEST_PATTERN_ONLY = True

# ===== SETUP BME280 SENSOR =====

sensor = None
if _bme_available and not TEST_PATTERN_ONLY:
    try:
        print("Initializing BME280...")
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c)
        sensor.sea_level_pressure = 1013.25
        print("BME280 initialized")
    except Exception as e:
        print(f"BME280 init error: {e}")

def read_bme280():
    """Read BME280 sensor data"""
    if sensor is None:
        return None, None, None
    try:
        temp = sensor.temperature
        humidity = sensor.humidity
        pressure = sensor.pressure
        return temp, humidity, pressure
    except Exception as e:
        print(f"BME280 read error: {e}")
        return None, None, None

# ===== SETUP E-INK DISPLAY =====

print("Initializing E-Ink display...")
spi = board.SPI()
epd_cs = board.D9
epd_dc = board.D10
epd_reset = None
epd_busy = None

display_bus = FourWire(spi, command=epd_dc, chip_select=epd_cs, reset=epd_reset, baudrate=1000000)
time.sleep(1)

# rotation=180 to match your orientation (since ruler was upside down at rotation=90)
display = adafruit_uc8151d.UC8151D(
    display_bus, width=296, height=128, rotation=180, busy_pin=epd_busy
)
display.auto_refresh = False

print(f"Display initialized: {display.width}x{display.height}")

# ===== DISPLAY FUNCTIONS =====

# Import display text only when needed (not in test pattern mode)
if not TEST_PATTERN_ONLY:
    from adafruit_display_text import label
    import terminalio

def show_half_black_half_white():
    """Render a half-black (left) / half-white (right) test image using two solid TileGrids.
    Performs a single refresh and then returns.
    """
    width = display.width
    height = display.height
    mid_x = width // 2

    group = displayio.Group()

    # Left half: solid black
    left_bitmap = displayio.Bitmap(mid_x, height, 1)
    left_palette = displayio.Palette(1)
    left_palette[0] = 0x000000
    left_tile = displayio.TileGrid(left_bitmap, pixel_shader=left_palette, x=0, y=0)
    group.append(left_tile)

    # Right half: solid white
    right_bitmap = displayio.Bitmap(width - mid_x, height, 1)
    right_palette = displayio.Palette(1)
    right_palette[0] = 0xFFFFFF
    right_tile = displayio.TileGrid(right_bitmap, pixel_shader=right_palette, x=mid_x, y=0)
    group.append(right_tile)

    display.root_group = group
    print("Refreshing display with half-black/half-white test pattern...")
    try:
        # Ensure panel allows a refresh now
        try:
            while hasattr(display, "time_to_refresh") and not display.time_to_refresh:
                time.sleep(0.1)
        except Exception:
            pass

        display.refresh()
        print("Test pattern shown.")
        # Wait until panel finishes update (time_to_refresh becomes True again)
        try:
            while hasattr(display, "time_to_refresh") and not display.time_to_refresh:
                time.sleep(0.1)
        except Exception:
            pass

        # Put panel to sleep to avoid artifacts when power is removed
        try:
            if hasattr(display, "sleep"):
                display.sleep()
        except Exception:
            pass

        # Give the panel and power rails a moment to settle before unplugging
        time.sleep(2)
    except RuntimeError as e:
        print(f"Refresh blocked: {e} (waiting for timer...)")

def create_display_group():
    """Create a fresh display group with current sensor readings"""
    # Read sensor first
    temp, humidity, pressure = read_bme280()
    
    g = displayio.Group()
    
    # White background
    background = displayio.Bitmap(display.width, display.height, 1)
    palette = displayio.Palette(1)
    palette[0] = 0xFFFFFF
    bg_sprite = displayio.TileGrid(background, pixel_shader=palette, x=0, y=0)
    g.append(bg_sprite)
    
    # Create text labels with current sensor data
    y_pos = 30
    line_spacing = 30
    
    # Temperature
    if temp is not None:
        temp_text = f"Temperature: {temp:.1f}C"
    else:
        temp_text = "Temperature: --.-C"
    
    temp_label = label.Label(
        terminalio.FONT,
        text=temp_text,
        color=0x000000,
        x=10,
        y=y_pos
    )
    g.append(temp_label)
    y_pos += line_spacing
    
    # Humidity
    if humidity is not None:
        humidity_text = f"Humidity: {humidity:.0f}%"
    else:
        humidity_text = "Humidity: --%"
    
    humidity_label = label.Label(
        terminalio.FONT,
        text=humidity_text,
        color=0x000000,
        x=10,
        y=y_pos
    )
    g.append(humidity_label)
    y_pos += line_spacing
    
    # Pressure
    if pressure is not None:
        pressure_text = f"Pressure: {pressure:.1f}hPa"
    else:
        pressure_text = "Pressure: ----hPa"
    
    pressure_label = label.Label(
        terminalio.FONT,
        text=pressure_text,
        color=0x000000,
        x=10,
        y=y_pos
    )
    g.append(pressure_label)
    
    return g, temp, humidity, pressure

# ===== MAIN LOOP =====

print("\n=== Simple E-Ink Display ===")
print(f"Display: {display.width}x{display.height}")
print(f"BME280 available: {sensor is not None}")

if TEST_PATTERN_ONLY:
    print("Mode: TEST_PATTERN_ONLY -> showing half-black/half-white pattern")
    show_half_black_half_white()
    # Keep device idle to preserve the image on E-Ink without repeated refreshes
    while True:
        time.sleep(60)
else:
    print("Mode: BME280 display")
    print("Update interval: 180 seconds\n")

    # Initial display
    print("Creating initial display...")
    group, temp, humidity, pressure = create_display_group()
    display.root_group = group

    print("Refreshing display...")
    try:
        display.refresh()
        print("Display refreshed!\n")
        if temp is not None:
            print(f"Initial: Temp: {temp:.1f}°C | Humidity: {humidity:.1f}% | Pressure: {pressure:.1f}hPa\n")
    except RuntimeError as e:
        print(f"Refresh blocked: {e} (waiting for timer...)\n")

    last_update = time.monotonic()

    while True:
        now = time.monotonic()
        
        if (now - last_update) >= 180:
            # Update every 180 seconds
            print("--- Updating Display ---")
            
            # Create fresh display group with new sensor readings
            group, temp, humidity, pressure = create_display_group()
            display.root_group = group
            
            if temp is not None:
                print(f"Temp: {temp:.1f}°C | Humidity: {humidity:.1f}% | Pressure: {pressure:.1f}hPa")
            else:
                print("Sensor read failed")
            
            # Refresh to show new display
            print("Refreshing display...")
            try:
                display.refresh()
                print("Display updated!\n")
            except RuntimeError as e:
                print(f"Refresh blocked: {e}\n")
            
            last_update = now
        
        time.sleep(1)
