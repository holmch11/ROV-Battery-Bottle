"""
RDML_Battery.py

Collects Battery Bottle Data on ESP32-S2 with CircuitPython, including:
- ACS770KCB-150U Current Sensor
- Voltage Divider for Battery Voltage
- BME280 Environmental Sensor
Also uses magnet/reed switch to trigger e-ink display print last 3 measurements.

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
2025/10/13 CEH Initial Version



####################################################################################
"""
import time
import board
import busio
import digitalio
import analogio
import wifi
import socketpool
import displayio
import terminalio
from adafruit_display_text import label
import adafruit_bmp280
import adafruit_il0373
import adafruit_requests
try:
    import adafruit_connection_manager as _acm
except ImportError:
    _acm = None
import alarm
import microcontroller
import sdcardio
import storage
import json
import os

# Configuration constants
CURRENT_THRESHOLD = 0.5  # Amps - adjust as needed
VOLTAGE_DIVIDER_A0 = (1000 + 2000) / 2000  # 1k + 2k / 2k
VOLTAGE_DIVIDER_A1 = (160000 + 40200) / 40200  # 160k + 40.2k / 40.2k
ACS770_SENSITIVITY = 0.01  # V/A for ACS770KCB-150U
ACS770_ZERO_CURRENT = 2.5  # V at zero current
EINK_REFRESH_MIN_INTERVAL = 180  # seconds
SLEEP_CHECK_INTERVAL = 60  # seconds
COULOMB_SAMPLE_RATE = 1  # samples per second

# I2C Slave Configuration
I2C_SLAVE_ADDRESS = 0x42  # Choose an available I2C address
I2C_BUFFER_SIZE = 256

# SD Card Management
MAX_LOG_FILE_SIZE_MB = 50  # Maximum size per log file in MB
MAX_TOTAL_LOG_SIZE_GB = 14  # Maximum total log size (leave 2GB free)
LOG_ROTATION_FILES = 10  # Number of log files to keep in rotation
SD_CHECK_INTERVAL = 3600  # Check SD space every hour (in seconds)

# Reed/magnet configuration
REED_PIN = board.D12
# True if magnet makes the pin read HIGH (active-high with pull-down). Set to False if your wiring is active-low.
REED_ACTIVE_HIGH = True


# Keep device awake after boot until first magnet trigger
DEBUG_PRINT_INTERVAL_S = 1.0

# WiFi credentials - set these
WIFI_SSID = "Jupiter"
WIFI_PASSWORD = "marinerobotics"
SERVER_URL = "http://rdml_jupiter.com/api/data"


class BitmapLoader:
    """Helper class to load a logo from BMP on disk, with a tiny placeholder fallback"""

    def __init__(self):
        self.logo_sprite = None
        self._file_handle = None  # Keep file open for OnDiskBitmap lifetime
        self._width = 0
        self._height = 0
        self.load_logo_from_disk()

    def _file_exists(self, path):
        try:
            with open(path, "rb") as _:
                return True
        except OSError:
            return False
        except Exception:
            return False

    def load_logo_from_disk(self):
        """Load logo.bmp from SD or internal flash using OnDiskBitmap."""
        try:
            candidates = ("/sd/logo.bmp", "/logo.bmp")
            for path in candidates:
                if self._file_exists(path):
                    # Keep file handle open for the lifetime of the TileGrid
                    self._file_handle = open(path, "rb")
                    odb = displayio.OnDiskBitmap(self._file_handle)
                    # ColorConverter handles 1-bit/8-bit BMP automatically
                    self.logo_sprite = displayio.TileGrid(
                        odb, pixel_shader=displayio.ColorConverter(), x=0, y=0
                    )
                    self._width = getattr(odb, "width", 0)
                    self._height = getattr(odb, "height", 0)
                    print(f"Loaded logo from {path} ({self._width}x{self._height})")
                    return
            # Fallback if no file found
            self.create_placeholder_bitmap()
        except Exception as e:
            print(f"Error loading logo.bmp: {e}")
            self.create_placeholder_bitmap()

    def create_placeholder_bitmap(self):
        """Create a simple placeholder bitmap if logo can't be loaded"""
        width = 148
        height = 128

        logo_bitmap = displayio.Bitmap(width, height, 2)
        logo_palette = displayio.Palette(2)
        logo_palette[0] = 0xFFFFFF  # White
        logo_palette[1] = 0x000000  # Black

        # Create a simple border and text placeholder
        # Border
        for x in range(width):
            logo_bitmap[x, 0] = 1  # Top border
            logo_bitmap[x, height - 1] = 1  # Bottom border
        for y in range(height):
            logo_bitmap[0, y] = 1  # Left border
            logo_bitmap[width - 1, y] = 1  # Right border

        # Simple diagonal pattern
        for i in range(min(width, height)):
            if i < width and i < height:
                logo_bitmap[i, i] = 1
            if (width - 1 - i) >= 0 and i < height:
                logo_bitmap[width - 1 - i, i] = 1

        print("Created placeholder bitmap")
        self.logo_sprite = displayio.TileGrid(
            logo_bitmap, pixel_shader=logo_palette, x=0, y=0
        )
        self._width = width
        self._height = height

    def get_logo_sprite(self):
        """Get a sprite for the logo that can be added to display group"""
        return self.logo_sprite

    def get_logo_width(self):
        return self._width


class I2CSlaveDevice:
    """I2C Slave implementation for ESP32-S2"""

    def __init__(self, address=I2C_SLAVE_ADDRESS):
        self.address = address
        self.data_buffer = bytearray(I2C_BUFFER_SIZE)
        self.data_ready = False
        self.last_measurements = []

        # Try to set up I2C slave mode (ESP32-S2 specific)
        try:
            # Note: CircuitPython on ESP32-S2 may need specific library for I2C slave
            # This is a conceptual implementation - you may need to use native ESP-IDF
            from busio import I2C

            self.i2c_slave = I2C(board.SCL, board.SDA, frequency=100000)
            print(f"I2C slave initialized at address 0x{address:02X}")
        except Exception as e:
            print(f"I2C slave setup failed: {e}")
            self.i2c_slave = None

    def update_measurement_data(
        self, temp, pressure, humidity, current, voltage, coulombs
    ):
        """Update the measurement data buffer for I2C reads"""
        # Store last 3 measurements
        measurement = {
            "temp": temp,
            "pressure": pressure,
            "humidity": humidity,
            "current": current,
            "voltage": voltage,
            "coulombs": coulombs,
            "timestamp": time.monotonic(),
        }

        self.last_measurements.append(measurement)
        if len(self.last_measurements) > 3:
            self.last_measurements.pop(0)  # Keep only last 3

        # Prepare data buffer for I2C transmission
        self.prepare_i2c_buffer()

    def prepare_i2c_buffer(self):
        """Prepare data buffer in JSON format for I2C transmission"""
        try:
            data_dict = {
                "measurements": self.last_measurements,
                "count": len(self.last_measurements),
                "device_id": "battery_monitor",
                "timestamp": time.monotonic(),
            }

            json_str = json.dumps(data_dict)
            json_bytes = json_str.encode("utf-8")

            # Clear buffer and copy data
            self.data_buffer[:] = b"\x00" * I2C_BUFFER_SIZE
            copy_len = min(len(json_bytes), I2C_BUFFER_SIZE - 1)
            self.data_buffer[:copy_len] = json_bytes[:copy_len]
            self.data_ready = True

        except Exception as e:
            print(f"I2C buffer preparation error: {e}")

    def get_last_three_formatted(self):
        """Get last three measurements formatted as requested"""
        if len(self.last_measurements) == 0:
            return "No measurements available\n"

        formatted_lines = []
        for i, measurement in enumerate(self.last_measurements):
            line = f"{measurement['pressure']:.1f},{measurement['humidity']:.1f},{measurement['temp']:.1f}"
            formatted_lines.append(line)

        return "\n".join(formatted_lines) + "\n"

    def handle_i2c_request(self):
        """Handle I2C read requests from master (Raspberry Pi)"""
        if not self.i2c_slave or not self.data_ready:
            return

        try:
            # This would be implemented using ESP32-S2 specific I2C slave functionality
            # For now, we'll prepare the data buffer
            pass
        except Exception as e:
            print(f"I2C request handling error: {e}")


class SDCardManager:
    def __init__(self):
        self.current_log_file = 0
        self.log_entries_count = 0
        self.last_space_check = 0
        self.max_file_size_bytes = MAX_LOG_FILE_SIZE_MB * 1024 * 1024
        self.max_total_size_bytes = MAX_TOTAL_LOG_SIZE_GB * 1024 * 1024 * 1024

    def get_log_filename(self, file_number=None):
        """Get log filename for current or specific file number"""
        if file_number is None:
            file_number = self.current_log_file
        return f"/sd/battery_log_{file_number:03d}.json"

    def get_file_size(self, filename):
        """Get file size in bytes, return 0 if file doesn't exist"""
        try:
            stat = os.stat(filename)
            return stat[6]  # st_size
        except OSError:
            return 0

    def get_total_log_size(self):
        """Calculate total size of all log files"""
        total_size = 0
        for i in range(LOG_ROTATION_FILES):
            filename = self.get_log_filename(i)
            total_size += self.get_file_size(filename)
        return total_size

    def get_oldest_log_file(self):
        """Find the oldest log file based on modification time"""
        oldest_file = None
        oldest_time = float("inf")

        for i in range(LOG_ROTATION_FILES):
            filename = self.get_log_filename(i)
            try:
                stat = os.stat(filename)
                mod_time = stat[8]  # st_mtime
                if mod_time < oldest_time:
                    oldest_time = mod_time
                    oldest_file = i
            except OSError:
                continue

        return oldest_file

    def rotate_log_files(self):
        """Rotate to next log file when current is full"""
        current_size = self.get_file_size(self.get_log_filename())

        if current_size >= self.max_file_size_bytes:
            print(f"Log file {self.current_log_file} reached max size, rotating...")

            # Check if we need to overwrite old files
            total_size = self.get_total_log_size()
            if total_size >= self.max_total_size_bytes:
                oldest_file = self.get_oldest_log_file()
                if oldest_file is not None:
                    try:
                        os.remove(self.get_log_filename(oldest_file))
                        print(f"Removed oldest log file: {oldest_file}")
                    except OSError as e:
                        print(f"Error removing old log file: {e}")

            # Move to next log file
            self.current_log_file = (self.current_log_file + 1) % LOG_ROTATION_FILES
            print(f"Switched to log file: {self.current_log_file}")

    def cleanup_old_logs(self):
        """Clean up old logs if total size exceeds limit"""
        current_time = time.monotonic()

        # Only check periodically to avoid constant file system access
        if current_time - self.last_space_check < SD_CHECK_INTERVAL:
            return

        self.last_space_check = current_time
        total_size = self.get_total_log_size()

        print(f"Total log size: {total_size / (1024*1024):.1f} MB")

        # Remove oldest files until we're under the limit
        while total_size > self.max_total_size_bytes:
            oldest_file = self.get_oldest_log_file()
            if oldest_file is None:
                break

            try:
                old_filename = self.get_log_filename(oldest_file)
                old_size = self.get_file_size(old_filename)
                os.remove(old_filename)
                total_size -= old_size
                print(
                    f"Removed old log file {oldest_file} ({old_size/1024/1024:.1f} MB)"
                )
            except OSError as e:
                print(f"Error removing old log: {e}")
                break

    def write_log_entry(self, data):
        """Write log entry with automatic rotation and cleanup"""
        try:
            # Check if we need to rotate files
            self.rotate_log_files()

            # Prepare log entry
            timestamp = time.monotonic()
            log_entry = {
                "timestamp": timestamp,
                "entry_number": self.log_entries_count,
            }
            if isinstance(data, dict):
                log_entry.update(data)

            # Write to current log file
            filename = self.get_log_filename()
            with open(filename, "a") as f:
                f.write(json.dumps(log_entry) + "\n")

            self.log_entries_count += 1

            # Periodic cleanup
            self.cleanup_old_logs()

            return True

        except Exception as e:
            print(f"SD log error: {e}")
            return False

    def get_last_measurements(self, count=3):
        """Retrieve last N measurements from log files"""
        measurements = []

        # Start with current log file and work backwards
        for file_offset in range(LOG_ROTATION_FILES):
            file_num = (self.current_log_file - file_offset) % LOG_ROTATION_FILES
            filename = self.get_log_filename(file_num)

            try:
                with open(filename, "r") as f:
                    lines = f.readlines()

                # Read from end of file backwards
                for line in reversed(lines):
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("event_type") in [
                            "active_measurement",
                            "sleep_measurement",
                        ]:
                            measurements.insert(0, entry)  # Insert at beginning
                            if len(measurements) >= count:
                                return measurements[-count:]  # Return last N
                    except (json.JSONDecodeError, KeyError):
                        continue

            except OSError:
                continue  # File doesn't exist, try next

        return measurements


class BatteryMonitor:
    def __init__(self):
        self.setup_hardware()
        self.coulombs = 0.0
        self.last_current_time = time.monotonic()
        # None means no refresh yet; first update should be allowed immediately
        self.last_eink_refresh = None
        self.above_threshold_start = None
        self.is_above_threshold = False
        self.data_log_count = 0

        # Track if we woke due to magnet (pin alarm)
        try:
            self.woke_from_magnet = isinstance(alarm.wake_alarm, alarm.pin.PinAlarm)
        except Exception:
            self.woke_from_magnet = False


        # Stay awake until first magnet trigger
        self._first_magnet_seen = False
        self._last_debug_print = 0.0

        # Initialize bitmap loader
        self.bitmap_loader = BitmapLoader()

    def setup_hardware(self):
        # Analog inputs
        self.current_pin = analogio.AnalogIn(board.A0)
        self.battery_pin = analogio.AnalogIn(board.A1)

        # Reed switch: active when magnet present
        self.reed_switch = digitalio.DigitalInOut(REED_PIN)
        self.reed_switch.direction = digitalio.Direction.INPUT
        # Configure pull so that the inactive state is held opposite to active state
        self.reed_switch.pull = (
            digitalio.Pull.DOWN if REED_ACTIVE_HIGH else digitalio.Pull.UP
        )

        # I2C for BMP280 (or BME280 if used)
        self.i2c = busio.I2C(board.SCL, board.SDA)
        try:
            # BMP280 provides temperature and pressure (no humidity)
            self.bme280 = adafruit_bmp280.Adafruit_BMP280_I2C(self.i2c)
        except Exception as e:
            print(f"BMP280 init failed: {e}")
            self.bme280 = None

        # I2C Slave setup
        self.i2c_slave = I2CSlaveDevice()

        # SPI for E-ink display
        self.spi = busio.SPI(board.SCK, board.MOSI, board.MISO)

        # E-ink display setup
        displayio.release_displays()
        self.display_bus = displayio.FourWire(
            self.spi,
            command=board.D6,
            chip_select=board.D9,
            reset=board.D10,
            baudrate=1000000,
        )

        self.display = adafruit_il0373.IL0373(
            self.display_bus,
            width=296,
            height=128,
            rotation=90,
            black_bits_inverted=False,
            color_bits_inverted=False,
            grayscale=True,
            refresh_time=1,
        )

        # SD card setup with enhanced management
        try:
            self.sd_cs = digitalio.DigitalInOut(board.D5)
            self.sdcard = sdcardio.SDCard(self.spi, self.sd_cs)
            self.vfs = storage.VfsFat(self.sdcard)
            storage.mount(self.vfs, "/sd")
            self.sd_manager = SDCardManager()
            self.sd_available = True
            print("SD card initialized with rotation management")

            # Log startup
            startup_data = {
                "event": "system_startup",
                "message": "Battery monitor started",
            }
            self.sd_manager.write_log_entry(startup_data)

        except Exception as e:
            print(f"SD card not available: {e}")
            self.sd_available = False
            self.sd_manager = None

        # Report wake cause
        try:
            wake = alarm.wake_alarm
            if isinstance(wake, alarm.pin.PinAlarm):
                print("Woke from PinAlarm (magnet)")
            elif isinstance(wake, alarm.time.TimeAlarm):
                print("Woke from TimeAlarm")
            else:
                print("Cold boot or unknown wake cause")
        except Exception:
            pass

        # WiFi setup
        self.setup_wifi()

    def setup_wifi(self):
        try:
            wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
            # Prefer connection manager if available; otherwise fallback to direct socketpool+ssl
            if _acm is not None:
                pool = _acm.get_radio_socketpool(wifi.radio)
                ssl_context = _acm.get_radio_ssl_context(wifi.radio)
            else:
                pool = socketpool.SocketPool(wifi.radio)
                try:
                    import ssl as _ssl
                    ssl_context = _ssl.create_default_context()
                except Exception:
                    ssl_context = None  # For HTTP endpoints this is fine

            self.pool = pool
            self.requests = adafruit_requests.Session(pool, ssl_context)
            print(f"Connected to WiFi: {wifi.radio.ipv4_address}")
        except Exception as e:
            print(f"WiFi connection failed: {e}")

    def read_current(self):
        """Read current from ACS770KCB-150U with voltage divider correction"""
        raw_value = self.current_pin.value
        voltage = (raw_value / 65535) * 3.3 * VOLTAGE_DIVIDER_A0
        # Convert voltage to current (ACS770KCB has 10mV/A sensitivity)
        current = (voltage - ACS770_ZERO_CURRENT) / ACS770_SENSITIVITY
        return max(0, current)  # Ensure non-negative

    def read_battery_voltage(self):
        """Read battery voltage with voltage divider correction"""
        raw_value = self.battery_pin.value
        voltage = (raw_value / 65535) * 3.3 * VOLTAGE_DIVIDER_A1
        return voltage

    def read_environmental(self):
        """Read environmental sensor data (BMP280: temp+pressure, humidity=0.0)"""
        try:
            if self.bme280 is None:
                raise RuntimeError("Environmental sensor not initialized")
            temp = self.bme280.temperature
            pressure = self.bme280.pressure
            # BMP280 has no humidity attribute; default to 0.0
            humidity = getattr(self.bme280, "relative_humidity", 0.0)
            return temp, pressure, humidity
        except Exception as e:
            print(f"Environmental read error: {e}")
            return 0, 0, 0

    def update_coulombs(self, current):
        """Update coulomb count when above threshold"""
        current_time = time.monotonic()
        if self.is_above_threshold:
            time_delta = current_time - self.last_current_time
            self.coulombs += current * time_delta
        self.last_current_time = current_time

    def send_data_wifi(self, data):
        """Send data via WiFi"""
        try:
            response = self.requests.post(SERVER_URL, json=data)
            print(f"WiFi data sent: {response.status_code}")
            response.close()
            return True
        except Exception as e:
            print(f"WiFi send error: {e}")
            return False

    def update_i2c_data(self, temp, pressure, humidity, current, voltage, coulombs):
        """Update I2C slave data buffer"""
        self.i2c_slave.update_measurement_data(
            temp, pressure, humidity, current, voltage, coulombs
        )

    def print_last_three_measurements(self):
        """Print last three measurements in requested format"""
        if self.sd_available and self.sd_manager:
            measurements = self.sd_manager.get_last_measurements(3)

            if not measurements:
                print("No measurements available")
                return

            print("Last 3 measurements (Pressure,Humidity,Temperature):")
            for measurement in measurements:
                pressure = measurement.get("pressure", 0)
                humidity = measurement.get("humidity", 0)
                temp = measurement.get("temperature", 0)
                print(f"{pressure:.1f},{humidity:.1f},{temp:.1f}")
        else:
            # Fallback to I2C slave buffer if SD not available
            formatted_data = self.i2c_slave.get_last_three_formatted()
            print("Last 3 measurements from I2C buffer:")
            print(formatted_data.strip())

    def log_all_data(self, data, event_type="measurement"):
        """Log all data to SD card with enhanced management"""
        if not self.sd_available or not self.sd_manager:
            return False

        # Add metadata
        enhanced_data = {
            "event_type": event_type,
            "log_count": self.data_log_count,
            "system_uptime": time.monotonic(),
        }
        if isinstance(data, dict):
            enhanced_data.update(data)

        success = self.sd_manager.write_log_entry(enhanced_data)
        if success:
            self.data_log_count += 1

        return success

    def create_display_bitmap(
        self, temp, pressure, humidity, current, voltage, coulombs
    ):
        """Create bitmap for e-ink display with logo from bitmaps.h"""
        # Create main display group
        group = displayio.Group()

        # Add logo bitmap from bitmaps.h (left side)
        logo_sprite = self.bitmap_loader.get_logo_sprite()
        if logo_sprite:
            group.append(logo_sprite)
        logo_w = self.bitmap_loader.get_logo_width() or 148
        text_x = max(logo_w + 2, 150)  # Ensure text clears the logo

        # Text on right side (starting at x=148)
        font = terminalio.FONT

        # Battery voltage
        voltage_label = label.Label(font, text=f"Batt: {voltage:.2f}V", color=0x000000)
        voltage_label.x = text_x
        voltage_label.y = 15
        group.append(voltage_label)

        # Current
        current_label = label.Label(font, text=f"Curr: {current:.2f}A", color=0x000000)
        current_label.x = text_x
        current_label.y = 30
        group.append(current_label)

        # Coulombs (converted to Amp-hours)
        coulomb_label = label.Label(
            font, text=f"Ah: {coulombs/3600:.3f}", color=0x000000
        )
        coulomb_label.x = text_x
        coulomb_label.y = 45
        group.append(coulomb_label)

        # Temperature
        temp_label = label.Label(font, text=f"Temp: {temp:.1f}C", color=0x000000)
        temp_label.x = text_x
        temp_label.y = 60
        group.append(temp_label)

        # Pressure
        pressure_label = label.Label(
            font, text=f"Pres: {pressure:.1f}hPa", color=0x000000
        )
        pressure_label.x = text_x
        pressure_label.y = 75
        group.append(pressure_label)

        # Humidity
        humidity_label = label.Label(font, text=f"Hum: {humidity:.1f}%", color=0x000000)
        humidity_label.x = text_x
        humidity_label.y = 90
        group.append(humidity_label)

        # Log count indicator
        log_label = label.Label(
            font, text=f"Logs: {self.data_log_count}", color=0x000000
        )
        log_label.x = text_x
        log_label.y = 105
        group.append(log_label)

        return group

    def update_display(self, temp, pressure, humidity, current, voltage, coulombs, *, force: bool = False):
        """Update e-ink display with rate limiting.

        Set force=True to bypass the rate limit (e.g., on magnet trigger).
        """
        current_time = time.monotonic()
        if (not force) and (self.last_eink_refresh is not None) and (
            current_time - self.last_eink_refresh < EINK_REFRESH_MIN_INTERVAL
        ):
            return

        try:
            display_group = self.create_display_bitmap(
                temp, pressure, humidity, current, voltage, coulombs
            )
            self.display.show(display_group)
            self.display.refresh()
            self.last_eink_refresh = current_time

            # Log display update
            display_data = {
                "event": "display_update",
                "temperature": temp,
                "pressure": pressure,
                "humidity": humidity,
                "current": current,
                "voltage": voltage,
                "coulombs": coulombs,
            }
            self.log_all_data(display_data, "display_update")

            print("E-ink display updated with logo")
        except Exception as e:
            print(f"Display update error: {e}")

    def main_loop(self):
        """Main monitoring loop"""
        while True:
            # If we just woke from the magnet, force an immediate display update once
            woke_trigger = False
            if getattr(self, "woke_from_magnet", False):
                woke_trigger = True
                self.woke_from_magnet = False  # One-shot

            current = self.read_current()
            voltage = self.read_battery_voltage()
            temp, pressure, humidity = self.read_environmental()

            # Debug: report reed value changes while awake
            try:
                reed_now = self.reed_switch.value
                if getattr(self, "_last_reed_value", None) is None:
                    self._last_reed_value = reed_now
                elif reed_now != self._last_reed_value:
                    print(f"Reed changed: {self._last_reed_value} -> {reed_now}")
                    self._last_reed_value = reed_now
            except Exception:
                pass


            # On first loop after boot, allow immediate e-ink update
            if not self._first_magnet_seen:
                self.update_display(
                    temp, pressure, humidity, current, voltage, self.coulombs, force=True
                )
                self.print_last_three_measurements()
                time.sleep(0.5)
                # Edge-detect: only count a rising edge (low→high) as the first trigger
                if not hasattr(self, '_reed_last_state'):
                    self._reed_last_state = self.reed_switch.value
                if self._reed_last_state == (not REED_ACTIVE_HIGH) and self.reed_switch.value == REED_ACTIVE_HIGH:
                    # Rising edge detected
                    self._first_magnet_seen = True
                    print("First magnet trigger (rising edge) detected; entering normal sleep mode.")
                    # Optional: debounce to avoid double-trigger
                    time.sleep(0.2)
                self._reed_last_state = self.reed_switch.value
                # Stay awake and print debug info
                now = time.monotonic()
                if (now - self._last_debug_print) >= DEBUG_PRINT_INTERVAL_S:
                    self._last_debug_print = now
                    try:
                        print(
                            "AWAKE:",
                            f"reed={self.reed_switch.value}",
                            f"I={current:.2f}A",
                            f"V={voltage:.2f}V",
                            f"T={temp:.1f}C",
                            f"P={pressure:.1f}hPa",
                            f"H={humidity:.1f}%",
                            f"Ah={self.coulombs/3600:.3f}",
                        )
                    except Exception as _e:
                        print(f"AWAKE print error: {_e}")
                time.sleep(0.1)
                continue  # Stay in loop until first magnet


            # Update I2C data buffer
            self.update_i2c_data(
                temp, pressure, humidity, current, voltage, self.coulombs
            )

            # Check if current is above threshold
            was_above_threshold = self.is_above_threshold
            self.is_above_threshold = current > CURRENT_THRESHOLD

            # Start coulomb counting when crossing threshold
            if self.is_above_threshold and not was_above_threshold:
                self.above_threshold_start = time.monotonic()
                print("Current above threshold - starting coulomb counting")

                # Log threshold crossing
                threshold_data = {
                    "event": "threshold_crossed",
                    "direction": "above",
                    "current": current,
                    "threshold": CURRENT_THRESHOLD,
                }
                self.log_all_data(threshold_data, "threshold_event")

            # Update coulombs if above threshold
            if self.is_above_threshold:
                self.update_coulombs(current)

                # Prepare comprehensive data
                data = {
                    "temperature": temp,
                    "pressure": pressure,
                    "humidity": humidity,
                    "current": current,
                    "voltage": voltage,
                    "coulombs": self.coulombs,
                    "amp_hours": self.coulombs / 3600,
                    "time_above_threshold": time.monotonic()
                    - self.above_threshold_start
                    if self.above_threshold_start
                    else 0,
                    "above_threshold": True,
                }

                # Send data via WiFi
                wifi_success = self.send_data_wifi(data)

                # Log all data with transmission status
                log_data = {}
                if isinstance(data, dict):
                    log_data.update(data)
                log_data["wifi_sent"] = wifi_success
                self.log_all_data(log_data, "active_measurement")

                # Check for magnet trigger
                if self.reed_switch.value:
                    self.update_display(
                        temp, pressure, humidity, current, voltage, self.coulombs, force=True
                    )
                    # Print last three measurements when magnet triggered
                    self.print_last_three_measurements()
                    time.sleep(1)  # Debounce

                time.sleep(1 / COULOMB_SAMPLE_RATE)

            else:
                # Below threshold - log transition if was previously above
                if was_above_threshold:
                    threshold_data = {
                        "event": "threshold_crossed",
                        "direction": "below",
                        "current": current,
                        "threshold": CURRENT_THRESHOLD,
                        "total_coulombs": self.coulombs,
                        "total_amp_hours": self.coulombs / 3600,
                    }
                    self.log_all_data(threshold_data, "threshold_event")

                # Log current state even when below threshold (less frequently)
                sleep_data = {
                    "temperature": temp,
                    "pressure": pressure,
                    "humidity": humidity,
                    "current": current,
                    "voltage": voltage,
                    "coulombs": self.coulombs,
                    "above_threshold": False,
                }
                self.log_all_data(sleep_data, "sleep_measurement")

                # Check for magnet trigger
                if self.reed_switch.value:
                    self.update_display(
                        temp, pressure, humidity, current, voltage, self.coulombs, force=True
                    )
                    # Print last three measurements when magnet triggered
                    self.print_last_three_measurements()
                    time.sleep(1)  # Debounce

                # Go to sleep after first magnet trigger
                self.enter_sleep_mode()

    def enter_sleep_mode(self):
        """Enter deep sleep with wake on pin change or timeout"""
        print("Entering sleep mode")

        # Log sleep entry
        sleep_data = {
            "event": "entering_sleep",
            "next_wake_check": SLEEP_CHECK_INTERVAL,
        }
        self.log_all_data(sleep_data, "power_management")

        # Set up alarms (wake on magnet level)
        pin_alarm = alarm.pin.PinAlarm(
            pin=REED_PIN,
            value=REED_ACTIVE_HIGH,
            pull=True,
        )
        time_alarm = alarm.time.TimeAlarm(
            monotonic_time=time.monotonic() + SLEEP_CHECK_INTERVAL
        )

        # Enter deep sleep
        alarm.exit_and_deep_sleep_until_alarms(pin_alarm, time_alarm)


# Main execution
if __name__ == "__main__":
    try:
        monitor = BatteryMonitor()
        monitor.main_loop()
    except Exception as e:
        print(f"Main loop error: {e}")
        # Try to log the error if SD is available
        try:
            if hasattr(monitor, "sd_manager") and monitor.sd_manager:
                error_data = {
                    "event": "system_error",
                    "error": str(e),
                    "action": "system_reset",
                }
                monitor.sd_manager.write_log_entry(error_data)
        except:
            pass
        # Reset after error
        microcontroller.reset()
