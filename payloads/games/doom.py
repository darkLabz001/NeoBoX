#!/usr/bin/env python3
# neo-name: DOOM
# neo-desc: Freedoom — play with the HAT buttons
# neo-icon: games
# neo-input: gpio
"""Launch Freedoom with a GPIO->keyboard bridge so the HAT controls it.
Controls: D-pad move | A fire | B use | X run | L/R strafe | Start menu | Select 'y'."""
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "neo" / "keybridge.py"

engine = next((e for e in ("/usr/games/chocolate-doom", "/usr/games/crispy-doom")
               if os.path.exists(e)), shutil.which("chocolate-doom"))
wad = next((w for w in ("/usr/share/games/doom/freedoom1.wad",
                        "/usr/share/games/doom/freedoom2.wad") if os.path.exists(w)), None)
if not engine:
    sys.exit("chocolate-doom not installed (sudo apt install chocolate-doom)")
if not wad:
    sys.exit("freedoom WAD not found (sudo apt install freedoom)")

print("Launching DOOM…")
print("  D-pad=move  A=fire  B=use  X=run  L/R=strafe  Start=menu  Select=y")
bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "doom"])
time.sleep(0.6)
try:
    subprocess.run([engine, "-iwad", wad, "-fullscreen"])
finally:
    try:
        bridge.send_signal(signal.SIGTERM)
    except Exception:
        pass
    subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], check=False)
print("DOOM exited.")
