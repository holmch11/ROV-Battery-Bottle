"""
RDML_Battery.py

Collects Battery Bottle Data on ESP32-S2 with CircuitPython, including:
- ACS770KCB-150U Current Sensor with 1k / 2k Voltage Divider
- 160kohm / 40.2kohm Voltage Divider for Battery Voltage
- BME280 Environmental Sensor
- SD Card logging with log rotation to limit total size
- WiFi upload of data to remote server
- I2C Slave interface to provide last 3 measurements to Raspberry Pi master
- 2.9" Monochrome Flexible E-ink Display from Adafruit
- Magnetic reed switch to trigger e-ink display print last 3 measurements.

Copyright (c) 2025
Created by Christopher Holm
holmch@oregonstate.edu

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Revision History
#####################################################################################
2025/12/01 CEH Initial Version



####################################################################################
"""

import time
import board
import displayio
from fourwire import FourWire
import adafruit_uc8151d
from adafruit_bme280 import basic as adafruit_bme280 
import os
import terminalio
from adafruit_display_text import label
import adafruit_imageload
import analogio
import json
try:
    from adafruit_bitmap_tools import bitmaptools
except Exception:
    bitmaptools = None

# Initialize I2C for BME280
i2c = board.I2C()
bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c)

# Initialize Feather E-ink Feather Friend
SD_CS = board.D5  # SD card chip select pin
SRAM_CS = board.D6  # SRAM chip select pin

displayio.release_displays()
spi = board.SPI()  # Uses SCK and MOSI
epd_cs = board.D9
epd_dc = board.D10
epd_reset = None
epd_busy = None

display_bus = FourWire(spi, command=epd_dc, chip_select=epd_cs, reset=epd_reset, baudrate=1000000)
time.sleep(1)

display = adafruit_uc8151d.UC8151D(
    display_bus, width=296, height=128, rotation=90, busy_pin=epd_busy
)

g = displayio.Group()

# Electrical measurement constants (matching test harness)
VOLTAGE_DIVIDER_A0 = (1000 + 2000) / 2000  # current sensor output divider
VOLTAGE_DIVIDER_A1 = (160000 + 40200) / 40200  # battery voltage divider
ACS770_SENSITIVITY = 0.0133  # V/A
ACS770_ZERO_CURRENT = 2.5  # V at zero current

# ADC pins
current_pin = analogio.AnalogIn(board.A0)
battery_pin = analogio.AnalogIn(board.A1)

# Total consumption (mAh) since last reset; try to persist on SD at /sd/total_mAh.txt
TOTAL_PATH = "/sd/total_mAh.txt"
total_mAh = 0.0
LAST_SAMPLE_PATH = "/sd/last_sample.json"
READINGS_PATH = "/sd/readings.txt"

def load_total_mAh():
    global total_mAh
    try:
        with open(TOTAL_PATH, "r") as f:
            total_mAh = float(f.read().strip())
    except Exception:
        total_mAh = 0.0

def save_total_mAh():
    try:
        with open(TOTAL_PATH, "w") as f:
            f.write(str(total_mAh))
    except Exception:
        pass

def load_last_sample():
    try:
        with open(LAST_SAMPLE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return None

def save_last_sample(sample):
    try:
        with open(LAST_SAMPLE_PATH, "w") as f:
            json.dump(sample, f)
    except Exception:
        pass

def append_reading_to_sd(entry):
    try:
        with open(READINGS_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

def load_last_readings(n=2):
    out = []
    try:
        with open(READINGS_PATH, "r") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        # parse JSON lines
        for ln in lines[-n:]:
            try:
                out.append(json.loads(ln))
            except Exception:
                # fallback parse: skip
                continue
    except Exception:
        pass
    return out

def read_current(pin):
    raw = pin.value
    v = (raw / 65535) * 3.3 * VOLTAGE_DIVIDER_A0
    amps = (v - ACS770_ZERO_CURRENT) / ACS770_SENSITIVITY
    return max(0.0, amps)

def read_voltage(pin):
    raw = pin.value
    v = (raw / 65535) * 3.3 * VOLTAGE_DIVIDER_A1
    return v


# Compose an in-RAM bitmap: logo on left, three latest BME280 readings on right
def compose_and_show_once(display, bme, logo_candidates=("/sd/logo_1bit.bmp", "/logo_1bit.bmp", "logo_1bit.bmp"), measurements=3, interval_s=1):
    # Behavior now: load last two readings from SD, take one new measurement
    load_total_mAh()
    global total_mAh
    prev_samples = load_last_readings(2)

    # Take a single new measurement
    try:
        temp = bme.temperature
        press = bme.pressure
        hum = bme.humidity
    except Exception:
        temp = None
        press = None
        hum = None
    try:
        amps = read_current(current_pin)
    except Exception:
        amps = 0.0
    try:
        volt = read_voltage(battery_pin)
    except Exception:
        volt = 0.0

    # timestamp (store full date + time)
    try:
        ts = int(time.time())
        t_struct = time.localtime(ts)
        timestamp = f"{t_struct[0]:04d}-{t_struct[1]:02d}-{t_struct[2]:02d} {t_struct[3]:02d}:{t_struct[4]:02d}:{t_struct[5]:02d}"
    except Exception:
        timestamp = "----:--:-- --:--:--"
        ts = 0

    # Trapezoidal integration using persisted last sample
    last = load_last_sample()
    if last and isinstance(last, dict) and "amps" in last and "ts" in last:
        dt = max(0, ts - int(last["ts"]))
        # hours
        dh = dt / 3600.0
        # trapezoid area (A) -> mAh
        total_mAh += ((float(last["amps"]) + amps) / 2.0) * dh * 1000.0
    else:
        # no previous sample; assume no integration
        pass

    # Save total and last sample once per run
    save_total_mAh()
    save_last_sample({"amps": amps, "ts": ts})

    # Create a canonical entry for SD and display
    new_entry = {
        "ts": timestamp,
        "amps": round(amps, 3),
        "volts": round(volt, 3),
        "press": round(press, 1) if press is not None else None,
        "temp": round(temp, 1) if temp is not None else None,
        "hum": round(hum, 0) if hum is not None else None,
        "total_mAh": int(total_mAh),
    }
    append_reading_to_sd(new_entry)

    # Build readings list with newest first: new, then previous entries (most recent first)
    readings = [new_entry]
    if prev_samples:
        # prev_samples comes oldest->newest; reverse to newest->oldest
        for p in reversed(prev_samples):
            readings.append(p)

    # Find logo path
    logo_path = None
    for p in logo_candidates:
        try:
            os.stat(p)
            logo_path = p
            break
        except Exception:
            continue

    disp_w = display.width
    disp_h = display.height

    # Destination in-RAM bitmap (1-bit: 2 colors)
    dest = displayio.Bitmap(disp_w, disp_h, 2)
    palette = displayio.Palette(2)
    palette[0] = 0xFFFFFF  # white
    palette[1] = 0x000000  # black

    # If imageload and a logo exists, load it and paste into dest (if bitmaptools available)
    if logo_path:
        try:
            logo_bmp, logo_pal = adafruit_imageload.load(logo_path, bitmap=displayio.Bitmap, palette=displayio.Palette)
            logo_w = logo_bmp.width
            logo_h = logo_bmp.height
            if bitmaptools:
                try:
                    bitmaptools.paste(logo_bmp, dest, 0, 0)
                except Exception:
                    # fallback: use TileGrid with group compositing below
                    logo_bmp = None
            else:
                # no bitmaptools: we'll composite by using a TileGrid for the logo
                logo_bmp = logo_bmp
        except Exception:
            logo_bmp = None
            logo_w = 0
            logo_h = 0
    else:
        logo_bmp = None
        logo_w = 0
        logo_h = 0

    # Prepare text labels (right side) from multiple readings
    text_x = min(logo_w + 8, disp_w - 120)
    # Build three lines per measurement: full timestamp, environmental, then electrical/total
    lines = []
    for r in readings:
        ts = r.get("ts", "----:--:-- --:--:--")
        p = r.get("press")
        t = r.get("temp")
        h = r.get("hum")
        a = r.get("amps")
        v = r.get("volts")
        tot = r.get("total_mAh")
        p_str = f"{p:.1f}hPa" if p is not None else "--"
        t_str = f"{t:.1f}C" if t is not None else "--"
        h_str = f"{int(h)}%" if h is not None else "--"
        # Format electrical values: current 1 decimal, voltage 2 decimals
        try:
            a_str = f"{float(a):.1f}"
        except Exception:
            a_str = "--"
        try:
            v_str = f"{float(v):.2f}"
        except Exception:
            v_str = "--"
        tot_str = f"{int(tot)}" if tot is not None else "--"
        lines.append(f"{ts}")
        lines.append(f"P:{p_str} T:{t_str} H:{h_str}")
        lines.append(f"I:{a_str}A V:{v_str}V Tot:{tot_str}mAh")

    # Build final group: if we couldn't paste into dest, use group layering
    if logo_bmp is None or bitmaptools is None:
        g = displayio.Group()
        # Add white background
        bg = displayio.TileGrid(dest, pixel_shader=palette)
        g.append(bg)
        # If a logo exists, show it left using TileGrid
        try:
            if logo_path:
                ondisk = displayio.OnDiskBitmap(logo_path)
                tg_logo = displayio.TileGrid(ondisk, pixel_shader=ondisk.pixel_shader, x=0, y=0)
                g.append(tg_logo)
        except Exception:
            pass

        # Add text labels using adafruit_display_text (stack vertically)
        for idx, ln in enumerate(lines):
            lab = label.Label(terminalio.FONT, text=ln, color=0x000000)
            lab.x = text_x
            # spread the readings evenly; baseline offset 12
            lab.y = 12 + idx * int((disp_h - 24) / max(1, len(lines)))
            g.append(lab)

        display.root_group = g
        try:
            display.refresh()
        except Exception:
            # some drivers auto-refresh on show
            pass
        return

    # If we reached here, bitmaptools.paste succeeded and dest contains logo; now render text onto dest
    # Create a TileGrid from dest and group
    tg = displayio.TileGrid(dest, pixel_shader=palette, x=0, y=0)
    g = displayio.Group()
    g.append(tg)

    # Add textual labels (these are rendered as separate TileGrids; they will composite over dest)
    for idx, ln in enumerate(lines):
        lab = label.Label(terminalio.FONT, text=ln, color=0x000000)
        lab.x = text_x
        lab.y = 12 + idx * int((disp_h - 24) / max(1, len(lines)))
        g.append(lab)

    display.root_group = g
    try:
        display.refresh()
    except Exception:
        pass


# Run composition repeatedly at ~200 second intervals (display update cadence)
SLEEP_SECONDS = 200
while True:
    try:
        # Recreate the display each cycle to ensure a full fresh update
        displayio.release_displays()
        time.sleep(0.05)
        display_bus = FourWire(spi, command=epd_dc, chip_select=epd_cs, reset=epd_reset, baudrate=1000000)
        time.sleep(0.05)
        display = adafruit_uc8151d.UC8151D(display_bus, width=296, height=128, rotation=90, busy_pin=epd_busy)
        compose_and_show_once(display, bme280)
    except Exception as e:
        print("Error composing/showing BMP:", e)
    try:
        time.sleep(SLEEP_SECONDS)
    except Exception:
        # If sleep interrupted, continue
        pass

