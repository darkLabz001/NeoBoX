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

# Use _key suffixes for keyboard mapping
cfg_path = Path(tempfile.gettempdir()) / "neo_retroarch_hotkeys.cfg"
cfg_content = [
    'video_fullscreen = "true"',
    'input_driver = "udev"',
    'input_enable_hotkey_key = "rshift"',
    'input_exit_emulator_key = "enter"',
    'input_player1_up_key = "up"',
    'input_player1_down_key = "down"',
    'input_player1_left_key = "left"',
    'input_player1_right_key = "right"',
    'input_player1_a_key = "x"',
    'input_player1_b_key = "z"',
    'input_player1_x_key = "s"',
    'input_player1_y_key = "a"',
    'input_player1_l_key = "q"',
    'input_player1_r_key = "w"',
    'input_player1_start_key = "enter"',
    'input_player1_select_key = "rshift"',
]
cfg_path.write_text("\n".join(cfg_content) + "\n")

# Start bridge as root
bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "retroarch"])
time.sleep(1.0)

try:
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
