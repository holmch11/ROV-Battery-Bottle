"""Boot-time USB control for true deep sleep"""
import time
import board
import digitalio

try:
    import storage
except Exception:
    storage = None
try:
    import usb_cdc
except Exception:
    usb_cdc = None

# Config
REED_PIN = board.D12
REED_ACTIVE_HIGH = True  # True if magnet makes D12 HIGH

# Read reed at boot
reed = digitalio.DigitalInOut(REED_PIN)
reed.direction = digitalio.Direction.INPUT
reed.pull = digitalio.Pull.DOWN if REED_ACTIVE_HIGH else digitalio.Pull.UP

magnet_present = reed.value if REED_ACTIVE_HIGH else (not reed.value)
time.sleep(0.01)

if not magnet_present:
    # Deployment mode: disable USB for true deep sleep
    if storage is not None:
        try:
            storage.disable_usb_drive()
        except Exception:
            pass
    if usb_cdc is not None:
        try:
            usb_cdc.disable()
        except Exception:
            pass
else:
    # Maintenance mode: keep USB enabled
    if usb_cdc is not None:
        try:
            usb_cdc.enable(console=True, data=False)
        except Exception:
            pass

reed.deinit()