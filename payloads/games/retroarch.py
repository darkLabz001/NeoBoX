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
print("  Combo: SELECT (hold) + START to exit back to Neo")

sink = hdmi_sink()
setvol(sink, GAME_VOL)

# Explicit configuration to ensure the virtual keyboard is used
cfg_path = Path(tempfile.gettempdir()) / "neo_retroarch_hotkeys.cfg"
cfg_content = [
    'video_driver = "gl"',
    'video_fullscreen = "true"',
    'input_driver = "sdl2"',
    'input_enable_hotkey = "rshift"',
    'input_exit_emulator = "enter"',
    'input_player1_up = "up"',
    'input_player1_down = "down"',
    'input_player1_left = "left"',
    'input_player1_right = "right"',
    'input_player1_a = "x"',
    'input_player1_b = "z"',
    'input_player1_x = "s"',
    'input_player1_y = "a"',
    'input_player1_l = "q"',
    'input_player1_r = "w"',
    'input_player1_start = "enter"',
    'input_player1_select = "rshift"',
    # Disable autoconfig so it doesn't fight our manual mapping
    'input_autodetect_enable = "false"',
]
cfg_path.write_text("\n".join(cfg_content) + "\n")

# Start bridge as root
bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "retroarch"])
time.sleep(1.5)

try:
    # Run retroarch with the hotkey override
    # -L (core) is not specified, it will open the menu
    subprocess.run([engine, "--appendconfig", str(cfg_path)])
finally:
    try:
        bridge.send_signal(signal.SIGTERM)
    except Exception: pass
    subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], check=False)
    if cfg_path.exists():
        cfg_path.unlink()
    setvol(sink, UI_VOL)

print("RetroArch exited.")
