"""Shared helpers for the game/emulator payloads.

Keeps each payload in payloads/games/ tiny and consistent: HDMI audio routing,
ROM selection, and the GPIO->keyboard bridge lifecycle (start bridge, run the
emulator, always tear the bridge down and restore UI volume) live here once.

Payloads use it via:  sys.path.insert(0, REPO); from neo import emu
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BRIDGE = REPO / "neo" / "keybridge.py"
UI_VOL = "1.3"   # HAT amp needs a boost; restored when a game exits


# --- audio ------------------------------------------------------------------
def hdmi_sink() -> str | None:
    """The pipewire sink id for the HAT's HDMI speakers (or None)."""
    try:
        out = subprocess.run(["wpctl", "status"], capture_output=True,
                             text=True, timeout=4).stdout
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


def set_volume(sink: str | None, vol: str):
    if sink:
        subprocess.run(["wpctl", "set-volume", sink, vol], check=False)


# --- ROM selection ----------------------------------------------------------
def pick_rom(argv: list[str], subdir: str, exts: tuple[str, ...]) -> str:
    """ROM path from argv[1] (the picker passes it), else the first match in
    ~/roms/<subdir>. Exits with a helpful message if there's nothing to run."""
    if len(argv) > 1 and os.path.exists(argv[1]):
        return argv[1]
    d = Path.home() / "roms" / subdir
    found: list[Path] = []
    if d.is_dir():
        for e in exts:
            found += sorted(d.glob("*" + e))
    if not found:
        sys.exit(f"No ROM in {d}. Upload one via the Web UI.")
    return str(found[0])


def fix_cue(rom: str):
    """A .cue is a text index pointing at a .bin; if the referenced data file is
    missing (common after a rename), repoint it at the .bin that's actually
    present, or explain what to upload."""
    p = Path(rom)
    if p.suffix.lower() != ".cue":
        return
    text = p.read_text(errors="replace")
    m = re.search(r'FILE\s+"([^"]+)"', text)
    referenced = p.parent / m.group(1) if m else None
    if referenced and referenced.exists():
        return
    bins = sorted(p.parent.glob("*.bin"))
    if not bins:
        sys.exit(
            "GAME DATA MISSING.\n"
            f"{p.name} is just a text index pointing to a .bin file, but no .bin\n"
            f"is present. Upload the actual game data (~hundreds of MB) to\n"
            f"{p.parent} via the Web UI.")
    new = re.sub(r'(FILE\s+")[^"]+(")', lambda mm: mm.group(1) + bins[0].name + mm.group(2),
                 text, count=1)
    p.write_text(new)
    print(f"Repointed {p.name} -> {bins[0].name}")


# --- launch lifecycle -------------------------------------------------------
def run_with_bridge(cmd: list[str], profile: str, game_vol: str = "0.85"):
    """Route audio, start the GPIO->keyboard bridge (as root), run `cmd`, then
    always tear the bridge down and restore the UI volume."""
    sink = hdmi_sink()
    set_volume(sink, game_vol)
    bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), profile])
    time.sleep(0.8)
    try:
        subprocess.run(cmd)
    finally:
        try:
            bridge.send_signal(signal.SIGTERM)
        except Exception:
            pass
        subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], check=False)
        set_volume(sink, UI_VOL)


def run_libretro(core: str | None, rom: str | None, game_vol: str = "0.85"):
    """Apply the RetroArch config (button map, RA login, etc.) and run a libretro
    `core` with `rom` — or, with both None, boot RetroArch to its own menu."""
    sys.path.insert(0, str(REPO))
    from neo import retroarch_cfg
    retroarch_cfg.apply()
    engine = shutil.which("retroarch") or "/usr/bin/retroarch"
    if not os.path.exists(engine):
        sys.exit("RetroArch not installed (Settings -> Deps).")
    if core and not os.path.exists(core):
        sys.exit(f"Emulator core missing at {core} (Settings -> Deps).")
    cmd = [engine]
    if core:
        cmd += ["-L", core]
    if rom:
        cmd.append(rom)
    run_with_bridge(cmd, "retroarch", game_vol)
