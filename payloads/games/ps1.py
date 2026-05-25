#!/usr/bin/env python3
# neo-name: PS1 Emulator
# neo-desc: PlayStation 1 (pcsx-rearmed, HLE BIOS)
# neo-icon: games
# neo-input: gpio
# neo-apt: retroarch
"""Launch a PS1 game in RetroArch + pcsx-rearmed (built-in HLE BIOS — no BIOS
file needed for most games). ROMs live in ~/roms/ps1 (upload via the Web UI).
Controls: D-pad=move  A/B/X/Y=face  L/R=bumpers  Start  Select  |  SELECT+START = exit."""
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "neo" / "keybridge.py"
ROMS = Path.home() / "roms" / "ps1"
CORE = "/usr/lib/aarch64-linux-gnu/libretro/pcsx_rearmed_libretro.so"
GAME_VOL = "0.85"
UI_VOL = "1.3"

engine = shutil.which("retroarch") or "/usr/bin/retroarch"
if not os.path.exists(engine):
    sys.exit("RetroArch not installed (Settings -> Deps).")
if not os.path.exists(CORE):
    sys.exit("pcsx-rearmed core missing at " + CORE)

# --- pick a ROM -------------------------------------------------------
rom = sys.argv[1] if len(sys.argv) > 1 and os.path.exists(sys.argv[1]) else ""
if not rom:
    found = (sorted(ROMS.glob("*.cue")) + sorted(ROMS.glob("*.pbp"))
             + sorted(ROMS.glob("*.chd"))) if ROMS.exists() else []
    if not found:
        sys.exit(f"No ROM in {ROMS}. Upload one via the Web UI.")
    rom = str(found[0])
rom_path = Path(rom)

# --- a .cue needs its .bin; fix name mismatches, error if data missing -
if rom_path.suffix.lower() == ".cue":
    folder = rom_path.parent
    text = rom_path.read_text(errors="replace")
    m = re.search(r'FILE\s+"([^"]+)"', text)
    referenced = folder / m.group(1) if m else None
    if not (referenced and referenced.exists()):
        bins = sorted(folder.glob("*.bin"))
        if not bins:
            sys.exit(
                "GAME DATA MISSING.\n"
                f"{rom_path.name} is just a text index pointing to a .bin file,\n"
                "but no .bin is present. Upload the actual game data file\n"
                f"(e.g. 'Digimon World (USA).bin', ~500MB) to {folder} via the Web UI.")
        new = re.sub(r'(FILE\s+")[^"]+(")', lambda mm: mm.group(1) + bins[0].name + mm.group(2),
                     text, count=1)
        rom_path.write_text(new)
        print(f"Repointed {rom_path.name} -> {bins[0].name}")


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


# RetroArch config: fullscreen, udev keyboard input matching the 'retroarch'
# keybridge profile, and SELECT(hotkey)+START = exit.
cfg = tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False)
cfg.write("\n".join([
    'video_fullscreen = "true"',
    'input_driver = "udev"',
    'menu_driver = "rgui"',
    'input_enable_hotkey_key = "rshift"',   # SELECT
    'input_exit_emulator_key = "enter"',    # +START
    'input_player1_up_key = "up"', 'input_player1_down_key = "down"',
    'input_player1_left_key = "left"', 'input_player1_right_key = "right"',
    'input_player1_a_key = "x"', 'input_player1_b_key = "z"',
    'input_player1_x_key = "s"', 'input_player1_y_key = "a"',
    'input_player1_l_key = "q"', 'input_player1_r_key = "w"',
    'input_player1_start_key = "enter"', 'input_player1_select_key = "rshift"',
    'input_menu_toggle_key = "f1"',
]) + "\n")
cfg.close()

print(f"Launching PS1: {rom_path.name}")
print("  D-pad=move  A/B/X/Y=face  L/R=bumpers  |  hold SELECT + START = exit")
sink = hdmi_sink()
setvol(sink, GAME_VOL)
bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "retroarch"])
time.sleep(0.8)
try:
    subprocess.run([engine, "-L", CORE, str(rom_path), "--appendconfig", cfg.name])
finally:
    try:
        bridge.send_signal(signal.SIGTERM)
    except Exception:
        pass
    subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], check=False)
    setvol(sink, UI_VOL)
    try:
        os.unlink(cfg.name)
    except Exception:
        pass
print("PS1 exited.")
