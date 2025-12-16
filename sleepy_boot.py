"""Boot configuration - Testing Mode"""
# Simplified boot.py for testing - no deep sleep/USB control
# Just remount SD card as writable so code.py can save files

try:
    import storage
except Exception:
    storage = None

# Remount SD card as writable so code.py can save files
if storage is not None:
    try:
        storage.remount("/sd", readonly=False)
        print("boot.py: SD card remounted as writable")
    except Exception as e:
        print(f"boot.py: SD remount skipped or failed: {e}")