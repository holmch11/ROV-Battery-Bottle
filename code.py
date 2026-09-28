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
2026/09/28 


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
import digitalio
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

REED_PIN = board.D12
REED_ACTIVE_HIGH = True
REED_DEBOUNCE_SECONDS = 0.03
MIN_DISPLAY_REFRESH_INTERVAL_SECONDS = 180
reed = digitalio.DigitalInOut(REED_PIN)
reed.direction = digitalio.Direction.INPUT
reed.pull = digitalio.Pull.DOWN if REED_ACTIVE_HIGH else digitalio.Pull.UP

# Rolling snapshot history on the SD card
READINGS_PATH = "/sd/readings.txt"
MAX_SAVED_READINGS = 4
CURRENT_THRESHOLD_AMPS = 0.8
BATTERY_PRESENT_VOLTAGE = 1.0
SAMPLE_INTERVAL_SECONDS = 1
SNAPSHOT_INTERVAL_SECONDS = 200
REED_POLL_INTERVAL_SECONDS = 0.01

draw_total_mAh = 0.0
draw_active = False
last_high_current_amps = None
last_high_current_time = None
last_reed_raw = reed.value
stable_reed_active = reed.value if REED_ACTIVE_HIGH else not reed.value
reed_raw_change_time = time.monotonic()

def detect_magnet_swipe(now):
    global last_reed_raw, stable_reed_active, reed_raw_change_time
    raw = reed.value
    if raw != last_reed_raw:
        last_reed_raw = raw
        reed_raw_change_time = now

    if now - reed_raw_change_time >= REED_DEBOUNCE_SECONDS:
        active = raw if REED_ACTIVE_HIGH else not raw
        if active != stable_reed_active:
            stable_reed_active = active
            return active
    return False

def load_last_readings(n=MAX_SAVED_READINGS):
    out = []
    try:
        with open(READINGS_PATH, "r") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        for ln in reversed(lines):
            try:
                out.insert(0, json.loads(ln))
            except Exception:
                continue
            if len(out) >= n:
                break
    except Exception:
        pass
    return out

def append_reading_to_sd(entry):
    readings = load_last_readings(MAX_SAVED_READINGS)
    readings.append(entry)
    readings = readings[-MAX_SAVED_READINGS:]
    try:
        with open(READINGS_PATH, "w") as f:
            for reading in readings:
                f.write(json.dumps(reading) + "\n")
    except Exception:
        pass

def read_current(pin):
    raw = pin.value
    v = (raw / 65535) * 3.3 * VOLTAGE_DIVIDER_A0
    amps = (v - ACS770_ZERO_CURRENT) / ACS770_SENSITIVITY
    return max(0.0, amps)

def read_voltage(pin):
    raw = pin.value
    v = (raw / 65535) * 3.3 * VOLTAGE_DIVIDER_A1
    return v


def read_environment(bme):
    try:
        return bme.temperature, bme.pressure, bme.humidity
    except Exception:
        return None, None, None

def make_timestamp():
    try:
        value = time.localtime()
        return f"{value[0]:04d}-{value[1]:02d}-{value[2]:02d} {value[3]:02d}:{value[4]:02d}:{value[5]:02d}"
    except Exception:
        return "----/-- --:--"

def build_reading(temp, press, hum, amps, volts):
    return {
        "ts": make_timestamp(),
        "amps": round(amps, 3),
        "volts": round(volts, 3),
        "press": round(press, 1) if press is not None else None,
        "temp": round(temp, 1) if temp is not None else None,
        "hum": round(hum, 0) if hum is not None else None,
    }

def display_readings(display, readings):
    group = displayio.Group()
    row_height = max(1, int((display.height - 16) / max(1, len(readings))))
    line_height = min(12, max(9, int((row_height - 4) / 4)))
    for index, reading in enumerate(reversed(readings[-3:])):
        timestamp = reading.get("ts", "")
        if len(timestamp) >= 16 and timestamp[4] == "-":
            timestamp = timestamp[5:7] + "/" + timestamp[8:10] + " " + timestamp[11:16]
        prefix = ("NOW", "-1", "-2")[index]
        temp = reading.get("temp")
        humidity = reading.get("hum")
        pressure = reading.get("press")
        volts = reading.get("volts")
        amps = reading.get("amps")
        lines = (
            f"{prefix} {timestamp}",
            f"T {temp:.1f}C  H {humidity:.0f}%" if temp is not None and humidity is not None else "T --  H --",
            f"P {pressure:.1f}hPa" if pressure is not None else "P --",
            f"V {volts:.2f}V  I {amps:.2f}A" if volts is not None and amps is not None else "V --  I --",
        )
        start_y = 8 + index * row_height
        for line_index, text in enumerate(lines):
            text_label = label.Label(terminalio.FONT, text=text, color=0x000000)
            text_label.x = 4
            text_label.y = start_y + line_index * line_height
            group.append(text_label)

    display.root_group = group
    try:
        display.refresh()
    except Exception:
        pass

def update_draw_total(amps, now):
    global draw_total_mAh, draw_active
    global last_high_current_amps, last_high_current_time
    if amps > CURRENT_THRESHOLD_AMPS:
        if draw_active and last_high_current_time is not None:
            elapsed_hours = max(0, now - last_high_current_time) / 3600.0
            draw_total_mAh += (last_high_current_amps + amps) * 0.5 * elapsed_hours * 1000.0
        draw_active = True
        last_high_current_amps = amps
        last_high_current_time = now
    else:
        draw_total_mAh = 0.0
        draw_active = False
        last_high_current_amps = None
        last_high_current_time = None

last_snapshot_time = None
last_sample_time = 0.0
last_display_refresh = None
display_initialized = False
while True:
    try:
        now = time.monotonic()
        if detect_magnet_swipe(now):
            if (
                display_initialized
                and last_display_refresh is not None
                and now - last_display_refresh >= MIN_DISPLAY_REFRESH_INTERVAL_SECONDS
                and read_current(current_pin) <= CURRENT_THRESHOLD_AMPS
            ):
                display_readings(display, load_last_readings(MAX_SAVED_READINGS))
                last_display_refresh = now

        if now - last_sample_time >= SAMPLE_INTERVAL_SECONDS:
            last_sample_time = now
            temperature, pressure, humidity = read_environment(bme280)
            current_amps = read_current(current_pin)
            battery_volts = read_voltage(battery_pin)
            update_draw_total(current_amps, now)

            if current_amps > CURRENT_THRESHOLD_AMPS:
                print(
                    "humidity={:.1f}% pressure={:.1f}hPa temperature={:.1f}C "
                    "battery_voltage={:.2f}V current={:.0f}mA draw_total={:.2f}mAh".format(
                        humidity if humidity is not None else 0.0,
                        pressure if pressure is not None else 0.0,
                        temperature if temperature is not None else 0.0,
                        battery_volts,
                        current_amps * 1000.0,
                        draw_total_mAh,
                    )
                )
            else:
                # Placeholder for real deep-sleep; just announce it for now while testing.
                print("sleep")
                if battery_volts >= BATTERY_PRESENT_VOLTAGE:
                    if last_snapshot_time is None or now - last_snapshot_time >= SNAPSHOT_INTERVAL_SECONDS:
                        reading = build_reading(
                            temperature, pressure, humidity, current_amps, battery_volts
                        )
                        append_reading_to_sd(reading)
                        last_snapshot_time = now

                if not display_initialized:
                    display_readings(display, load_last_readings(MAX_SAVED_READINGS))
                    display_initialized = True
                    last_display_refresh = now

                if battery_volts < BATTERY_PRESENT_VOLTAGE:
                    last_snapshot_time = None
    except Exception as error:
        print("Measurement error:", error)
    time.sleep(REED_POLL_INTERVAL_SECONDS)

