#!/usr/bin/env python3
# neo-name: PS1 Emulator
# neo-desc: PlayStation 1 (pcsx-rearmed, HLE BIOS)
# neo-icon: games
# neo-input: gpio
# neo-apt: retroarch
# neo-roms: ps1
# neo-romext: .cue .pbp .chd
"""PlayStation 1 in RetroArch + pcsx-rearmed (built-in HLE BIOS — no BIOS file
needed for most games). ROMs live in ~/roms/ps1 (upload via the Web UI).
Controls: D-pad=move  A/B/X/Y=face  L/R=bumpers  Start  Select  |  SELECT + START = exit."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from neo import emu

CORE = "/usr/lib/aarch64-linux-gnu/libretro/pcsx_rearmed_libretro.so"

rom = emu.pick_rom(sys.argv, "ps1", (".cue", ".pbp", ".chd"))
emu.fix_cue(rom)
print(f"Launching PS1: {Path(rom).name}")
print("  D-pad=move  A/B/X/Y=face  L/R=bumpers  |  hold SELECT + START = exit")
emu.run_libretro(CORE, rom)
print("PS1 exited.")
