#!/usr/bin/env python3
"""GPIO -> uinput keyboard bridge so the HAT buttons drive external games.
Run as root (needs /dev/uinput). Usage: keybridge.py [profile]
"""
from __future__ import annotations

import json
import signal
import sys
import time
from pathlib import Path

import gpiod
from gpiod.line import Bias, Direction, Value
from evdev import UInput, ecodes as e

BUTTONS = Path(__file__).resolve().parent.parent / "config" / "buttons.json"

PROFILES = {
    "doom": {
        "UP": e.KEY_UP, "DOWN": e.KEY_DOWN,
        "LEFT": e.KEY_COMMA, "RIGHT": e.KEY_DOT,
        "L": e.KEY_LEFT, "R": e.KEY_RIGHT,
        "A": e.KEY_LEFTCTRL, "B": e.KEY_SPACE, "X": e.KEY_LEFTSHIFT,
        "Y": e.KEY_Y,
        "START": e.KEY_ESC, "SELECT": e.KEY_ENTER,
    },
    "retroarch": {
        "UP": e.KEY_UP, "DOWN": e.KEY_DOWN,
        "LEFT": e.KEY_LEFT, "RIGHT": e.KEY_RIGHT,
        "A": e.KEY_X, "B": e.KEY_Z, "X": e.KEY_S, "Y": e.KEY_A,
        "L": e.KEY_Q, "R": e.KEY_W,
        "START": e.KEY_ENTER, "SELECT": e.KEY_RSHIFT,
    },
    "ps1": {
        "UP": e.KEY_UP, "DOWN": e.KEY_DOWN,
        "LEFT": e.KEY_LEFT, "RIGHT": e.KEY_RIGHT,
        "A": e.KEY_S, "B": e.KEY_D, "X": e.KEY_A, "Y": e.KEY_W,
        "L": e.KEY_Q, "R": e.KEY_E,
        "START": e.KEY_ENTER, "SELECT": e.KEY_TAB,
        "EXIT": e.KEY_ESC,
    },
}

def main():
    profile = sys.argv[1] if len(sys.argv) > 1 else "doom"
    keymap = PROFILES.get(profile, PROFILES["doom"])

    cfg = json.loads(BUTTONS.read_text())
    chip_path = "/dev/" + cfg.get("chip", "gpiochip0")
    pins = {a: int(p) for a, p in cfg["pins"].items()
            if int(p) >= 0 and a in keymap}
    pressed_level = 0 if cfg.get("active_low", True) else 1

    ui = UInput({e.EV_KEY: sorted(set(keymap.values()))}, name="RetroArch Keyboard")

    plist = sorted(pins.values())
    settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP)
    req = gpiod.request_lines(chip_path, consumer="neobox-keybridge",
                              config={p: settings for p in plist})
    action_of = {p: a for a, p in pins.items()}

    run = {"v": True}
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: run.update(v=False))

    # PANIC EXIT: holding START+SELECT+L+R together force-kills the game even if
    # it has frozen (the bridge polls GPIO directly, so it never freezes).
    panic_pins = {pins[a] for a in ("START", "SELECT", "L", "R") if a in pins}
    import os
    panic_hold = 0

    prev = {p: 1 for p in plist}
    while run["v"]:
        vals = req.get_values()
        pressed = set()
        for i, p in enumerate(plist):
            lvl = 1 if vals[i] == Value.ACTIVE else 0
            if lvl == pressed_level:
                pressed.add(p)
            if lvl != prev[p]:
                ui.write(e.EV_KEY, keymap[action_of[p]], 1 if lvl == pressed_level else 0)
                ui.syn()
                prev[p] = lvl
        if panic_pins and panic_pins <= pressed:
            panic_hold += 1
            if panic_hold > 40:   # ~0.3s held
                os.system("pkill -9 -f 'retroarch|chocolate-doom|mednafen|pcsx'")
                break
        else:
            panic_hold = 0
        time.sleep(0.008)
    ui.close()

if __name__ == "__main__":
    main()
