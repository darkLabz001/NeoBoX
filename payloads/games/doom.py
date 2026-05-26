#!/usr/bin/env python3
# neo-name: DOOM
# neo-desc: Freedoom — play with the HAT buttons
# neo-icon: games
# neo-input: gpio
# neo-apt: chocolate-doom, freedoom
"""Freedoom via chocolate-doom with the GPIO->keyboard bridge.
Controls: D-pad move | A fire | B use | X run | L/R strafe | Start menu | Select enter | Y yes."""
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from neo import emu

engine = next((e for e in ("/usr/games/chocolate-doom", "/usr/games/crispy-doom")
               if os.path.exists(e)), shutil.which("chocolate-doom"))
wad = next((w for w in ("/usr/share/games/doom/freedoom1.wad",
                        "/usr/share/games/doom/freedoom2.wad") if os.path.exists(w)), None)
if not engine:
    sys.exit("chocolate-doom not installed (Settings -> Deps).")
if not wad:
    sys.exit("freedoom WAD not found (Settings -> Deps).")

print("Launching DOOM…")
print("  Joy=move/strafe  L/R=turn  A=fire  B=use  X=run  Start=menu  Select=enter  Y=yes")
# -nomusic: the OPL music synth crackles/underruns on a Pi 3B+; SFX stay clean.
emu.run_with_bridge([engine, "-iwad", wad, "-fullscreen", "-nomusic"], "doom", game_vol="1.0")
print("DOOM exited.")
