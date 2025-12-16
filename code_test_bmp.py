"""
ROV Battery Monitor - E-Ink Display with Sensor Logging
- Reads sensors, composes /sd/logo.bmp with rolling readings, displays on e-ink.
- Runs 2 rounds for testing: one at startup, one after 3 minutes.
- Uses RTC for timestamps and SD card for data logging.
"""
import time
import rtc
import board
import busio
import digitalio
import analogio
import displayio
import fourwire
import terminalio
import json
import os
import adafruit_uc8151d
import adafruit_sdcard
import storage
from adafruit_bme280 import basic as adafruit_bme280


# ========== CONFIG ==========
VOLTAGE_DIVIDER_A0 = (1000 + 2000) / 2000  # Current sensor output divider
VOLTAGE_DIVIDER_A1 = (160000 + 40200) / 40200  # Battery voltage divider
ACS770_SENSITIVITY = 0.0133  # V/A
ACS770_ZERO_CURRENT = 2.5  # V at zero current

UPDATE_PERIOD_S = 180  # 3 minutes
TEST_ROUNDS = 2  # Run twice then stop

# Default file paths (may be overridden after storage detection)
LOGO_LEFT_PATH = "/sd/logo_1bit.bmp"
BMP_OUT_PATH = "/sd/logo.bmp"
READINGS_PATH = "/sd/readings.txt"

CANVAS_W = 296
CANVAS_H = 128

# ========== MINIMAL 5x7 FONT ==========
FONT_5x7 = {
    " ": [0,0,0,0,0],
    "0": [0x3E,0x51,0x49,0x45,0x3E],
    "1": [0x00,0x42,0x7F,0x40,0x00],
    "2": [0x42,0x61,0x51,0x49,0x46],
    "3": [0x21,0x41,0x45,0x4B,0x31],
    "4": [0x18,0x14,0x12,0x7F,0x10],
    "5": [0x27,0x45,0x45,0x45,0x39],
    "6": [0x3C,0x4A,0x49,0x49,0x30],
    "7": [0x01,0x71,0x09,0x05,0x03],
    "8": [0x36,0x49,0x49,0x49,0x36],
    "9": [0x06,0x49,0x49,0x29,0x1E],
    "A": [0x7E,0x11,0x11,0x11,0x7E],
    "C": [0x3E,0x41,0x41,0x41,0x22],
    "H": [0x7F,0x08,0x08,0x08,0x7F],
    "I": [0x00,0x41,0x7F,0x41,0x00],
    "P": [0x7F,0x09,0x09,0x09,0x06],
    "T": [0x01,0x01,0x7F,0x01,0x01],
    "V": [0x1F,0x20,0x40,0x20,0x1F],
    ":": [0x00,0x36,0x36,0x00,0x00],
    ".": [0x00,0x40,0x60,0x00,0x00],
    "%": [0x43,0x33,0x08,0x66,0x61],
    "/": [0x40,0x30,0x0C,0x03,0x00],
    "-": [0x08,0x08,0x08,0x08,0x08],
}

# ========== RTC HELPERS ==========
def init_rtc_if_needed():
    """Initialize RTC to current date/time if not already set (or clock looks stale)."""
    r = rtc.RTC()
    now = r.datetime
    # Check if RTC looks uninitialized (year < 2020) or you can prompt user to set
    if now.tm_year < 2020:
        # Set to a default start time; user can override via REPL before running
        # Format: time.struct_time((year, mon, mday, hour, min, sec, wday, yday, isdst))
        # Example: Oct 21, 2025, 12:00:00 (Monday=0)
        default_time = time.struct_time((2025, 10, 21, 12, 0, 0, 0, -1, -1))
        r.datetime = default_time
        print(f"RTC initialized to default: {format_time(r.datetime)}")
        print("To set manually, in REPL: import rtc, time; rtc.RTC().datetime = time.struct_time((YYYY,MM,DD,HH,MM,SS,0,-1,-1))")
    else:
        print(f"RTC already set: {format_time(now)}")

def format_time(t):
    """Format time.struct_time as HH:MM:SS"""
    return f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"

def get_timestamp():
    """Get current RTC time as formatted string HH:MM:SS"""
    return format_time(rtc.RTC().datetime)

def _font_char(ch):
    return FONT_5x7.get(ch, FONT_5x7[" "])

# ========== 1-BIT BMP UTILITIES ==========
def _row_stride_bytes(width):
    bpr = (width + 7) // 8
    return ((bpr + 3) // 4) * 4

def _set_bit(buf, width, x, y, value):
    if x < 0 or y < 0 or x >= CANVAS_W or y >= CANVAS_H:
        return
    stride = _row_stride_bytes(width)
    byte_index = y * stride + (x // 8)
    bit = 7 - (x % 8)
    if value:
        buf[byte_index] |= (1 << bit)
    else:
        buf[byte_index] &= ~(1 << bit)

def _draw_char(buf, x, y, ch):
    cols = _font_char(ch)
    for cx in range(5):
        col_bits = cols[cx]
        for cy in range(7):
            pixel_on = (col_bits >> cy) & 1
            _set_bit(buf, CANVAS_W, x + cx, y + cy, pixel_on)
    return x + 6

def _draw_text(buf, x, y, text):
    cx = x
    for ch in text:
        if ch == "\n":
            y += 9
            cx = x
            continue
        cx = _draw_char(buf, cx, y, ch)

def _write_bmp_1bit(path, width, height, topdown_buf):
    """Write a 1-bit BMP file"""
    stride = _row_stride_bytes(width)
    img_size = stride * height
    file_size = 14 + 40 + 8 + img_size
    pixel_offset = 14 + 40 + 8
    
    with open(path, "wb") as f:
        # BITMAPFILEHEADER
        f.write(b"BM")
        f.write(file_size.to_bytes(4, "little"))
        f.write((0).to_bytes(2, "little"))
        f.write((0).to_bytes(2, "little"))
        f.write(pixel_offset.to_bytes(4, "little"))
        # BITMAPINFOHEADER
        f.write((40).to_bytes(4, "little"))
        # Write width and height as signed integers
        width_bytes = width.to_bytes(4, "little") if width >= 0 else (width + 0x100000000).to_bytes(4, "little")
        height_bytes = height.to_bytes(4, "little") if height >= 0 else (height + 0x100000000).to_bytes(4, "little")
        f.write(width_bytes)
        f.write(height_bytes)
        f.write((1).to_bytes(2, "little"))
        f.write((1).to_bytes(2, "little"))
        f.write((0).to_bytes(4, "little"))
        f.write(img_size.to_bytes(4, "little"))
        f.write((2835).to_bytes(4, "little"))
        f.write((2835).to_bytes(4, "little"))
        f.write((2).to_bytes(4, "little"))
        f.write((0).to_bytes(4, "little"))
        # Color table
        f.write(bytes([255, 255, 255, 0]))
        f.write(bytes([0, 0, 0, 0]))
        # Pixel data bottom-up
        for row in range(height - 1, -1, -1):
            start = row * stride
            f.write(topdown_buf[start:start + stride])

def _read_bmp_1bit(path):
    """Read a 1-bit BMP and return width, height, stride, pixel data, and orientation"""
    with open(path, "rb") as f:
        data = f.read()
    if data[0:2] != b"BM":
        raise ValueError("Not a BMP")
    pixel_offset = int.from_bytes(data[10:14], "little")
    header_size = int.from_bytes(data[14:18], "little")
    if header_size != 40:
        raise ValueError("Unsupported BMP header")
    # Read as unsigned, then interpret as signed
    width_raw = int.from_bytes(data[18:22], "little")
    width = width_raw if width_raw < 0x80000000 else width_raw - 0x100000000
    height_raw = int.from_bytes(data[22:26], "little")
    height = height_raw if height_raw < 0x80000000 else height_raw - 0x100000000
    planes = int.from_bytes(data[26:28], "little")
    bpp = int.from_bytes(data[28:30], "little")
    if planes != 1 or bpp != 1:
        raise ValueError("BMP must be 1-bit")
    bottom_up = height > 0
    w = abs(width)
    h = abs(height)
    stride = _row_stride_bytes(w)
    pix = memoryview(data)[pixel_offset: pixel_offset + stride * h]
    return (w, h, stride, pix, bottom_up)

def _blit_logo_onto(buf, logo_path, dest_x, dest_y):
    """Blit logo BMP onto the canvas buffer"""
    lw, lh, lstride, lpix, bottom_up = _read_bmp_1bit(logo_path)
    max_w = min(lw, CANVAS_W - dest_x)
    max_h = min(lh, CANVAS_H - dest_y)
    for y in range(max_h):
        src_row = (lh - 1 - y) if bottom_up else y
        lrow_start = src_row * lstride
        for x in range(max_w):
            byte_index = lrow_start + (x // 8)
            bit = 7 - (x % 8)
            bit_on = (lpix[byte_index] >> bit) & 1
            _set_bit(buf, CANVAS_W, dest_x + x, dest_y + y, bit_on)

# ========== SENSOR READS ==========
def read_current(adc_pin):
    raw = adc_pin.value
    v = (raw / 65535) * 3.3 * VOLTAGE_DIVIDER_A0
    amps = (v - ACS770_ZERO_CURRENT) / ACS770_SENSITIVITY
    return max(0, amps)

def read_voltage(adc_pin):
    raw = adc_pin.value
    v = (raw / 65535) * 3.3 * VOLTAGE_DIVIDER_A1
    return v

def read_env(i2c):
    """Read temperature, pressure, humidity from BME280"""
    bme = adafruit_bme280.Adafruit_BME280_I2C(i2c)
    bme.sea_level_pressure = 1013.25
    return bme.temperature, bme.pressure, bme.humidity

# ========== ROLLING READINGS ==========
def load_readings():
    """Load the last 3 readings from file"""
    try:
        with open(READINGS_PATH, "r") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        return lines[-3:]
    except Exception:
        return []

def save_readings(lines):
    """Save the last 3 readings to file"""
    with open(READINGS_PATH, "w") as f:
        for ln in lines[-3:]:
            f.write(ln + "\n")

def format_reading(curr, volt, press, temp, hum):
    """Format reading as 3 lines: timestamp, I+V, P+T+H"""
    timestamp = get_timestamp()
    i_str = f"{curr:.2f}" if curr is not None else "--"
    v_str = f"{volt:.2f}" if volt is not None else "--"
    p_str = f"{press:.1f}" if press is not None else "--"
    t_str = f"{temp:.1f}" if temp is not None else "--"
    h_str = f"{hum:.0f}" if hum is not None else "--"
    line1 = timestamp
    line2 = f"I:{i_str}A V:{v_str}V"
    line3 = f"P:{p_str} T:{t_str}C H:{h_str}%"
    return f"{line1}\n{line2}\n{line3}"

# ========== COMPOSE & DISPLAY ==========
def compose_bmp_with_logo(readings_text, logo_path, out_path):
    """Compose BMP with logo on left and readings on right"""
    stride = _row_stride_bytes(CANVAS_W)
    buf = bytearray([0x00] * (stride * CANVAS_H))  # White background
    if _file_exists(logo_path):
        _blit_logo_onto(buf, logo_path, 0, 0)
    # Find logo width
    assumed_logo_w = 0
    for x in range(CANVAS_W):
        col_has_black = False
        for y in range(CANVAS_H):
            byte_index = y * stride + (x // 8)
            bit = 7 - (x % 8)
            if (buf[byte_index] >> bit) & 1:
                col_has_black = True
                break
        if col_has_black:
            assumed_logo_w = x
    text_x = min(assumed_logo_w + 6, CANVAS_W - 1)
    
    # Each reading is 3 lines (timestamp, I+V, P+T+H); spacing between readings
    line_height = 9  # height per text line
    reading_spacing = 2  # extra gap between readings
    lines_per_reading = 3
    reading_height = lines_per_reading * line_height + reading_spacing
    
    # How many readings fit?
    available_height = CANVAS_H - 8  # leave 8px top margin
    max_readings = available_height // reading_height
    
    # Take the last N readings that fit
    to_draw = readings_text[-max_readings:] if len(readings_text) > max_readings else readings_text
    
    y0 = 8
    for i, reading in enumerate(to_draw):
        # Each reading can be multi-line (split by \n)
        y_pos = y0 + i * reading_height
        _draw_text(buf, text_x, y_pos, reading.upper())
    
    _write_bmp_1bit(out_path, CANVAS_W, CANVAS_H, buf)

def show_bmp(display, path):
    """Display a BMP file on the e-ink screen"""
    bmp = displayio.OnDiskBitmap(path)
    tg = displayio.TileGrid(bmp, pixel_shader=bmp.pixel_shader, x=0, y=0)
    g = displayio.Group()
    g.append(tg)
    display.root_group = g
    display.refresh()

# ========== SD MOUNT HELPER ==========
def ensure_sd_writable():
    """Ensure SD card mounted at /sd is writable.
    Only attempts remount; never grabs the CS pin to avoid pin conflicts.
    Returns True if writable, else False.
    """
    # Fast path: try writing a tiny file
    try:
        with open("/sd/.writetest", "w") as f:
            f.write("ok")
        os.remove("/sd/.writetest")
        return True
    except Exception:
        pass

    # Try to remount writable (works when CP auto-mounted read-only)
    try:
        storage.remount("/sd", readonly=False)
        # Verify again
        with open("/sd/.writetest", "w") as f:
            f.write("ok")
        os.remove("/sd/.writetest")
        return True
    except Exception:
        return False

# ========== STORAGE HELPER ==========
def _file_exists(path):
    try:
        os.stat(path)
        return True
    except Exception:
        return False

# ========== SETUP ==========
print("ROV Battery Monitor starting...")

# Initialize RTC
init_rtc_if_needed()

spi = board.SPI()
while not spi.try_lock():
    pass
spi.configure(baudrate=24000000)
spi.unlock()

# Mount SD card (ensure writable without touching CS pin)
if not ensure_sd_writable():
    print("ERROR: SD card required but not writable")
    raise RuntimeError("SD card required")

# File paths
LOGO_LEFT_PATH = "/sd/logo_1bit.bmp"
BMP_OUT_PATH = "/sd/logo.bmp"
READINGS_PATH = "/sd/readings.txt"

# I2C for sensors
i2c = busio.I2C(board.SCL, board.SDA)

# E-ink display
displayio.release_displays()
display_bus = fourwire.FourWire(spi, command=board.D10, chip_select=board.D9, reset=board.D5, baudrate=1000000)
display = adafruit_uc8151d.UC8151D(display_bus, width=296, height=128, rotation=90, busy_pin=None)

# ADC pins
current_pin = analogio.AnalogIn(board.A0)
battery_pin = analogio.AnalogIn(board.A1)

# Load existing readings
readings = load_readings()
if not readings:
    readings = []

# ========== MAIN TEST LOOP ==========
for round_num in range(1, TEST_ROUNDS + 1):
    print(f"=== Round {round_num} ===")
    
    # Read sensors
    curr = read_current(current_pin)
    volt = read_voltage(battery_pin)
    temp_c, press_hpa, hum = read_env(i2c)
    
    # Format and update rolling buffer
    reading_text = format_reading(curr, volt, press_hpa, temp_c, hum)
    readings.append(reading_text)
    readings = readings[-10:]
    save_readings(readings)
    
    # Compose BMP and display
    compose_bmp_with_logo(readings, LOGO_LEFT_PATH, BMP_OUT_PATH)
    show_bmp(display, BMP_OUT_PATH)
    print(f"Round {round_num} complete")
    
    if round_num < TEST_ROUNDS:
        time.sleep(UPDATE_PERIOD_S)

print("Test complete")
while True:
    time.sleep(60)
