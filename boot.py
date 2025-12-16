"""Boot configuration - Testing Mode"""
# Simplified boot.py for testing - no deep sleep/USB control
# Mount SD card as writable so code.py can save files

import board
import sdcardio
import storage

# Mount SD card at /sd as writable
try:
    sd = sdcardio.SDCard(board.SPI(), board.D5)
    vfs = storage.VfsFat(sd)
    storage.mount(vfs, "/sd")
    print("boot.py: SD card mounted as writable at /sd")
except Exception as e:
    print(f"boot.py: SD mount failed: {e}")