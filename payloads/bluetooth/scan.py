#!/usr/bin/env python3
# neo-name: BT Scan
# neo-desc: Scan for Bluetooth devices
import os, sys, shutil
if shutil.which("bluetoothctl"):
    os.execvp("bash", ["bash", "-c", "timeout 15 bluetoothctl --timeout 15 scan on; bluetoothctl devices"])
sys.exit("bluetoothctl not available.")
