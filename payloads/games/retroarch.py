#!/usr/bin/env python3
# neo-name: RetroArch
# neo-desc: Multi-system emulator
# neo-icon: games
# neo-input: gpio
# neo-apt: retroarch, retroarch-assets, libretro-core-info
"""Launch RetroArch with a GPIO->keyboard bridge.
Controls: D-pad move | A,B,X,Y buttons | L/R bumpers | SELECT + START to Exit."""
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "neo" / "keybridge.py"
GAME_VOL = "0.80"
UI_VOL = "1.3"

engine = shutil.which("retroarch")
if not engine:
    for p in ["/usr/bin/retroarch", "/usr/local/bin/retroarch"]:
        if os.path.exists(p):
            engine = p
            break

if not engine:
    sys.exit("RetroArch not found. Use Settings -> Deps to install it.")

def hdmi_sink():
    try:
        out = subprocess.run(["wpctl", "status"], capture_output=True, text=True, timeout=4).stdout
        in_sinks = False
        for line in out.splitlines():
            if "Sinks:" in line: in_sinks = True; continue
            if "Sources:" in line: in_sinks = False
            if in_sinks and "hdmi" in line.lower():
                m = re.findall(r"\d+", line)
                if m: return m[0]
    except Exception: pass
    return None

def setvol(sink, v):
    if sink: subprocess.run(["wpctl", "set-volume", sink, v], check=False)

print("Launching RetroArch...")
print("  D-pad=navigate  A=OK  B=back  |  Settings > Achievements to sign in")
print("  Exit: hold SELECT + START   (panic: START+SELECT+L+R)")

# Write button map + udev input + rgui menu + RetroAchievements into the main
# config (reliable; preserves a saved RA login).
sys.path.insert(0, str(REPO))
from neo import retroarch_cfg
retroarch_cfg.apply()

sink = hdmi_sink()
setvol(sink, GAME_VOL)

# Start bridge as root
bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "retroarch"])
time.sleep(1.0)

try:
    subprocess.run([engine])   # no content -> boots to the menu (for RA setup)
finally:
    try:
        bridge.send_signal(signal.SIGTERM)
    except Exception:
        pass
    subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], check=False)
    setvol(sink, UI_VOL)

print("RetroArch exited.")
