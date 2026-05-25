#!/usr/bin/env python3
# neo-name: DOOM
# neo-desc: Freedoom — play with the HAT buttons
# neo-icon: games
# neo-input: gpio
"""Launch Freedoom with a GPIO->keyboard bridge so the HAT controls it.
Controls: D-pad move | A fire | B use | X run | L/R strafe | Start menu | Select 'y'."""
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "neo" / "keybridge.py"
GAME_VOL = "0.75"     # Doom's dense mix clips at the UI's boosted level; drop it
UI_VOL = "1.3"        # restore on exit

engine = next((e for e in ("/usr/games/chocolate-doom", "/usr/games/crispy-doom")
               if os.path.exists(e)), shutil.which("chocolate-doom"))
wad = next((w for w in ("/usr/share/games/doom/freedoom1.wad",
                        "/usr/share/games/doom/freedoom2.wad") if os.path.exists(w)), None)
if not engine:
    sys.exit("chocolate-doom not installed (sudo apt install chocolate-doom)")
if not wad:
    sys.exit("freedoom WAD not found (sudo apt install freedoom)")


def hdmi_sink():
    try:
        out = subprocess.run(["wpctl", "status"], capture_output=True, text=True,
                             timeout=4).stdout
        in_sinks = False
        for line in out.splitlines():
            if "Sinks:" in line:
                in_sinks = True
                continue
            if "Sources:" in line:
                in_sinks = False
            if in_sinks and "hdmi" in line.lower():
                m = re.findall(r"\d+", line)
                if m:
                    return m[0]
    except Exception:
        pass
    return None


def setvol(sink, v):
    if sink:
        subprocess.run(["wpctl", "set-volume", sink, v], check=False)


print("Launching DOOM…")
print("  Joy=move/strafe  L/R=turn  A=fire  B=use  X=run  Start=menu  Select=enter  Y=yes")
sink = hdmi_sink()
setvol(sink, GAME_VOL)
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
    setvol(sink, UI_VOL)
print("DOOM exited.")
