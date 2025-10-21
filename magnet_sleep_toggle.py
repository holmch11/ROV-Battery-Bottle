"""
Simple BME280 + Magnet Sleep Test (ESP32-S2, CircuitPython)

Behavior:
- Starts awake, reads BME280 sensor every few seconds
- When D12 goes HIGH (magnet present), debounces and goes to deep sleep
- Wakes after 2 minutes, reads sensor again, repeats

Hardware:
- Adafruit Feather ESP32-S2
- BME280 sensor on I2C (default SDA/SCL pins)
- Reed/magnet switch on D12 (pulls HIGH when magnet is present)

Note: For true deep sleep (USB/serial disappear), use boot.py to disable USB at boot.
Without boot.py, this will do "pretend" deep sleep (useful for testing with serial monitor).
"""

import time
import board
import digitalio
import alarm
try:
    import busio
    import adafruit_bme280.advanced as adafruit_bme280
    _bme_available = True
except ImportError:
    _bme_available = False
    print("BME280 library not found. Install adafruit-circuitpython-bme280")

# Config
REED_PIN = board.D12
REED_ACTIVE_HIGH = True  # True if magnet makes D12 HIGH
DEBOUNCE_MS = 50         # Debounce window
SLEEP_SECONDS = 120      # 2 minutes
SENSOR_READ_INTERVAL = 3 # Read sensor every 3 seconds while awake

# LED for status (if available)
_led = None
for led_name in ("LED", "D13"):
    if hasattr(board, led_name):
        try:
            _led = digitalio.DigitalInOut(getattr(board, led_name))
            _led.direction = digitalio.Direction.OUTPUT
            break
        except Exception:
            pass

# Reed switch setup
reed = digitalio.DigitalInOut(REED_PIN)
reed.direction = digitalio.Direction.INPUT
reed.pull = digitalio.Pull.DOWN if REED_ACTIVE_HIGH else digitalio.Pull.UP

# BME280 sensor setup
sensor = None
if _bme_available:
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c)
        sensor.sea_level_pressure = 1013.25  # Adjust for your location
        print("BME280 sensor initialized")
    except Exception as e:
        print(f"BME280 init error: {e}")
        sensor = None

def read_sensor():
    """Read and print BME280 data"""
    if sensor is None:
        print("Sensor not available")
        return
    try:
        temp_c = sensor.temperature
        humidity = sensor.humidity
        pressure = sensor.pressure
        print(f"Temp: {temp_c:.1f}°C | Humidity: {humidity:.1f}% | Pressure: {pressure:.1f} hPa")
    except Exception as e:
        print(f"Sensor read error: {e}")

def is_magnet_present():
    """Check if magnet is present (debounced)"""
    raw_value = reed.value
    return raw_value if REED_ACTIVE_HIGH else (not raw_value)

def wait_for_magnet():
    """Wait for debounced magnet detection, return True when magnet is stable present"""
    last_raw = reed.value
    last_change = time.monotonic()
    
    while True:
        now = time.monotonic()
        current_raw = reed.value
        
        # Detect state change
        if current_raw != last_raw:
            last_raw = current_raw
            last_change = now
        
        # Check if stable for debounce period
        if (now - last_change) * 1000.0 >= DEBOUNCE_MS:
            is_active = current_raw if REED_ACTIVE_HIGH else (not current_raw)
            if is_active:
                return True
        
        # Blink LED while waiting
        if _led is not None:
            _led.value = (int(now * 2) % 2) == 0
        
        time.sleep(0.01)

def go_to_sleep(seconds):
    """Enter deep sleep for the specified duration"""
    print(f"\n→ Going to DEEP SLEEP for {seconds} seconds...")
    print("   (If using boot.py without magnet at reset, USB will disappear)")
    
    if _led is not None:
        _led.value = False
    
    # Deinit peripherals
    reed.deinit()
    if sensor is not None:
        try:
            sensor._i2c.deinit()
        except Exception:
            pass
    
    time.sleep(0.2)
    
    # Deep sleep with timer alarm
    time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + seconds)
    alarm.exit_and_deep_sleep_until_alarms(time_alarm)
    
    # This line only executes in "pretend" deep sleep (USB still connected)
    print("   (Pretend deep sleep - USB still connected)")

# Check wake cause
wake_alarm = alarm.wake_alarm
if isinstance(wake_alarm, alarm.time.TimeAlarm):
    print("\n=== WOKE FROM DEEP SLEEP (Timer) ===\n")
else:
    print("\n=== COLD BOOT OR RESET ===\n")

# Turn on LED to show we're awake
if _led is not None:
    _led.value = True

print("BME280 + Magnet Sleep Test")
print(f"- Reed on D12, active={'HIGH' if REED_ACTIVE_HIGH else 'LOW'}")
print(f"- Reading sensor every {SENSOR_READ_INTERVAL}s")
print(f"- Wave magnet to trigger {SLEEP_SECONDS}s deep sleep\n")

# Main loop: read sensor and wait for magnet
last_read = time.monotonic()

while True:
    now = time.monotonic()
    
    # Read sensor at interval
    if (now - last_read) >= SENSOR_READ_INTERVAL:
        read_sensor()
        last_read = now
    
    # Check for magnet (non-blocking check with short timeout)
    if is_magnet_present():
        print("\n✓ Magnet detected! Waiting for stable signal...")
        wait_for_magnet()
        print("✓ Magnet confirmed (debounced)")
        go_to_sleep(SLEEP_SECONDS)
        # After wake, this restarts from the top
    
    time.sleep(0.05)
