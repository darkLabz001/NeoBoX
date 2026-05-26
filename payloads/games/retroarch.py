#!/usr/bin/env python3
# neo-name: RetroArch
# neo-desc: Multi-system emulator (boots to menu)
# neo-icon: games
# neo-input: gpio
# neo-apt: retroarch, retroarch-assets, libretro-core-info
"""Boot RetroArch to its own menu — load any content or sign in to
RetroAchievements (Settings > Achievements).
Controls: D-pad navigate | A=OK B=back | L/R bumpers | SELECT + START to exit."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from neo import emu

print("Launching RetroArch (menu)…")
print("  D-pad=navigate  A=OK  B=back  |  hold SELECT + START = exit")
emu.run_libretro(None, None, game_vol="0.80")   # no content -> RetroArch menu
print("RetroArch exited.")
