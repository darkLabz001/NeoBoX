#!/usr/bin/env python3
# neo-name: RetroArch
# neo-desc: Multi-system emulator
# neo-icon: games
# neo-input: gpio
# neo-apt: retroarch, retroarch-assets, libretro-core-info
"""Launch RetroArch with a GPIO->keyboard bridge.
Controls: D-pad move | A,B,X,Y buttons | L/R bumpers | Start+Select to Exit."""
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
    # Try common Pi locations if not in PATH
    for p in ["/usr/bin/retroarch", "/usr/local/bin/retroarch"]:
        if os.path.exists(p):
            engine = p
            break

if not engine:
    sys.exit("RetroArch not found. Install it with: sudo apt install retroarch")

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

print("Launching RetroArch...")
print("  Combo: SELECT + START to exit back to Neo")

sink = hdmi_sink()
setvol(sink, GAME_VOL)

# Create a temporary config file for hotkeys to ensure Start+Select exit works
# keybridge.py maps SELECT to rshift and START to enter
cfg_path = Path(tempfile.gettempdir()) / "neo_retroarch_hotkeys.cfg"
cfg_path.write_text(
    'input_enable_hotkey = "rshift"\n'
    'input_exit_emulator = "enter"\n'
)

bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "retroarch"])
time.sleep(0.6)
try:
    # Run retroarch with the hotkey override
    subprocess.run([engine, "--appendconfig", str(cfg_path)])
finally:
    try:
        bridge.send_signal(signal.SIGTERM)
    except Exception:
        pass
    subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], check=False)
    if cfg_path.exists():
        cfg_path.unlink()
    setvol(sink, UI_VOL)

print("RetroArch exited.")
