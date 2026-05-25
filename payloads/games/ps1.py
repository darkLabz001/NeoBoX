#!/usr/bin/env python3
# neo-name: PS1 Emulator
# neo-desc: PlayStation 1 (Mednafen)
# neo-icon: games
# neo-input: gpio
# neo-needs: rom_path
# neo-apt: mednafen
"""Launch Mednafen PS1 with a GPIO->keyboard bridge.
Controls: D-pad move | A=X, B=O, X=Square, Y=Triangle | SELECT+START to Exit."""
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
GAME_VOL = "0.80"
UI_VOL = "1.3"

engine = shutil.which("mednafen")
if not engine:
    sys.exit("Mednafen not found. Use Settings -> Deps to install it.")

rom = sys.argv[1] if len(sys.argv) > 1 else ""
if not rom or not os.path.exists(rom):
    # If no ROM provided, we'll try to find any .cue or .pbp in the default folder
    roms_dir = Path.home() / "roms" / "ps1"
    if roms_dir.exists():
        found = list(roms_dir.glob("*.cue")) + list(roms_dir.glob("*.pbp"))
        if found:
            rom = str(found[0])
        else:
            sys.exit(f"No ROM found in {roms_dir}. Please provide a path.")
    else:
        sys.exit("No ROM path provided and ~/roms/ps1/ does not exist.")

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

print(f"Launching PS1: {os.path.basename(rom)}...")
print("  Combo: SELECT + START to exit back to Neo")

sink = hdmi_sink()
setvol(sink, GAME_VOL)

# Start bridge as root
bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "ps1"])
time.sleep(1.0)

try:
    # -fs 1 (fullscreen), -video.driver opengl
    # Mednafen uses ESC to exit by default.
    # We map START+SELECT in keybridge to ESC for the PS1 profile.
    subprocess.run([engine, "-fs", "1", "-video.driver", "opengl", rom])
finally:
    try:
        bridge.send_signal(signal.SIGTERM)
    except Exception: pass
    subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], check=False)
    setvol(sink, UI_VOL)

print("Emulator exited.")
