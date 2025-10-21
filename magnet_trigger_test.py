"""
Magnet trigger diagnostic for ESP32-S2 (CircuitPython)

- Monitors D12 (reed/magnet switch)
- Debounces input and prints clean state changes
- Blinks/toggles onboard LED (if available) on magnet active
- Shows timing between edges to help identify bounce or noise

Usage
-----
1) Save this file somewhere on your host PC (it's already in the repo).
2) To run on the device, copy it to the board as code.py (after backing up your app):
   - Rename your current code.py on CIRCUITPY to code_main.py
   - Copy this file as code.py
   - Observe the Serial console (115200) to see prints
3) When done, restore your original code.py.

Adjust REED_ACTIVE_HIGH if your wiring uses active-low logic.
"""

import time
import board
import digitalio
try:
    import alarm
except Exception:
    alarm = None

# Configuration
REED_PIN = board.D12
REED_ACTIVE_HIGH = True   # Set False if your reed pulls low when magnet is present
DEBOUNCE_MS = 30          # Debounce window
PRINT_INTERVAL_S = 0.5    # Periodic status print

# Optional LED (ESP32-S2 boards may use board.LED or board.D13)
_led = None
for led_name in ("LED", "D13"):
    if hasattr(board, led_name):
        try:
            _led = digitalio.DigitalInOut(getattr(board, led_name))
            _led.direction = digitalio.Direction.OUTPUT
            break
        except Exception:
            _led = None

# Reed input with appropriate pull
reed = digitalio.DigitalInOut(REED_PIN)
reed.direction = digitalio.Direction.INPUT
reed.pull = digitalio.Pull.DOWN if REED_ACTIVE_HIGH else digitalio.Pull.UP

# Helpers

def is_active():
    return reed.value if REED_ACTIVE_HIGH else (not reed.value)

last_raw = reed.value
stable_state = is_active()
last_change = time.monotonic()
last_print = 0.0

print("Magnet trigger test starting...")
print(f"Active level: {'HIGH' if REED_ACTIVE_HIGH else 'LOW'} on D12")
print("Bring a magnet near the reed switch to see state changes.")

while True:
    now = time.monotonic()
    raw = reed.value

    # Edge on raw signal: start debounce timer
    if raw != last_raw:
        last_raw = raw
        last_change = now

    # After debounce window, accept new stable state
    if (now - last_change) * 1000.0 >= DEBOUNCE_MS:
        new_state = is_active()
        if new_state != stable_state:
            stable_state = new_state
            if _led is not None:
                _led.value = stable_state
            print(
                (
                    "MAGNET ACTIVE" if stable_state else "magnet inactive"
                ) + f" | raw={raw} | t={now:.3f}s"
            )

    # Periodic status print
    if (now - last_print) >= PRINT_INTERVAL_S:
        last_print = now
        if _led is not None:
            _led.value = stable_state
        print(
            f"status: {'ACTIVE' if stable_state else 'idle  '} | raw={raw} | pull={'DOWN' if REED_ACTIVE_HIGH else 'UP'}"
        )

    time.sleep(0.01)
