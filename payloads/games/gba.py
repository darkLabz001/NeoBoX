#!/usr/bin/env python3
# neo-name: GBA Emulator
# neo-desc: Game Boy Advance (mGBA, built-in BIOS)
# neo-icon: games
# neo-input: gpio
# neo-apt: retroarch, libretro-mgba
# neo-roms: gba
# neo-romext: .gba .zip
"""Game Boy Advance in RetroArch + mGBA (built-in BIOS — no BIOS file needed).
ROMs live in ~/roms/gba (upload via the Web UI; .gba or zipped).
Controls: D-pad=move  A/B=face  L/R=bumpers  Start  Select  |  SELECT + START = exit."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from neo import emu

CORE = "/usr/lib/aarch64-linux-gnu/libretro/mgba_libretro.so"

rom = emu.pick_rom(sys.argv, "gba", (".gba", ".zip"))
print(f"Launching GBA: {Path(rom).name}")
print("  D-pad=move  A/B=face  L/R=bumpers  |  hold SELECT + START = exit")
emu.run_libretro(CORE, rom)
print("GBA exited.")
