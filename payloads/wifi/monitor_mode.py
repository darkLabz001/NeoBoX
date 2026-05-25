#!/usr/bin/env python3
# neo-name: Monitor Mode
# neo-desc: Put an interface into monitor mode (airmon-ng)
# neo-needs: iface
import os, sys, shutil
ifc = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NEO_IFACE", "wlan1")).strip() or "wlan1"
if not shutil.which("airmon-ng"): sys.exit("aircrack-ng not installed.")
os.execvp("sudo", ["sudo", "-n", "airmon-ng", "start", ifc])
