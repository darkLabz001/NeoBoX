#!/usr/bin/env python3
# neo-name: GBA Emulator
# neo-desc: Game Boy Advance (mGBA, built-in BIOS)
# neo-icon: games
# neo-input: gpio
# neo-apt: retroarch, libretro-mgba
# neo-roms: gba
# neo-romext: .gba .zip
"""Launch a GBA game in RetroArch + mGBA (built-in BIOS — no BIOS file needed).
ROMs live in ~/roms/gba (upload via the Web UI; .gba or zipped).
Controls: D-pad=move  A/B=face  L/R=bumpers  Start  Select  |  SELECT + START = exit."""
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
ROMS = Path.home() / "roms" / "gba"
CORE = "/usr/lib/aarch64-linux-gnu/libretro/mgba_libretro.so"
GAME_VOL = "0.85"
UI_VOL = "1.3"

engine = shutil.which("retroarch") or "/usr/bin/retroarch"
if not os.path.exists(engine):
    sys.exit("RetroArch not installed (Settings -> Deps).")
if not os.path.exists(CORE):
    sys.exit("mGBA core missing at " + CORE + " (Settings -> Deps).")

# --- pick a ROM (argv[1] from the picker, else first found) -----------
rom = sys.argv[1] if len(sys.argv) > 1 and os.path.exists(sys.argv[1]) else ""
if not rom:
    found = (sorted(ROMS.glob("*.gba")) + sorted(ROMS.glob("*.zip"))) if ROMS.exists() else []
    if not found:
        sys.exit(f"No ROM in {ROMS}. Upload one via the Web UI.")
    rom = str(found[0])
rom_path = Path(rom)


def hdmi_sink():
    try:
        out = subprocess.run(["wpctl", "status"], capture_output=True, text=True, timeout=4).stdout
        in_sinks = False
        for line in out.splitlines():
            if "Sinks:" in line:
                in_sinks = True
                continue
            if "Sources:" in line:
                in_sinks = False
            if in_sinks and "hdmi" in line.lower():
                mm = re.findall(r"\d+", line)
                if mm:
                    return mm[0]
    except Exception:
        pass
    return None


def setvol(sink, v):
    if sink:
        subprocess.run(["wpctl", "set-volume", sink, v], check=False)


# Write the HAT button map + udev input + rgui menu + RetroAchievements into the
# main RetroArch config (reliable; preserves the saved RA login).
sys.path.insert(0, str(REPO))
from neo import retroarch_cfg
retroarch_cfg.apply()

print(f"Launching GBA: {rom_path.name}")
print("  D-pad=move  A/B=face  L/R=bumpers  |  hold SELECT + START = exit")
sink = hdmi_sink()
setvol(sink, GAME_VOL)
bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "retroarch"])
time.sleep(0.8)
try:
    subprocess.run([engine, "-L", CORE, str(rom_path)])
finally:
    try:
        bridge.send_signal(signal.SIGTERM)
    except Exception:
        pass
    subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], check=False)
    setvol(sink, UI_VOL)
print("GBA exited.")
