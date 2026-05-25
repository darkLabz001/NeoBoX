#!/usr/bin/env python3
"""GPIO -> uinput keyboard bridge so the HAT buttons drive external games.

Run as root (needs /dev/uinput).  Usage:  keybridge.py [profile]
NeoBoX releases its own GPIO hold before starting this, and kills it after the
game exits. Reads the verified pin map from config/buttons.json.

DOOM controls:
  D-pad = move/menu   A = fire(Ctrl)   B = use(Space)   X = run(Shift)
  Y = enter/select    Start = menu(Esc)   Select = 'y' (quit-confirm)
  L/R = strafe (, .)
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
        "UP": e.KEY_UP, "DOWN": e.KEY_DOWN, "LEFT": e.KEY_LEFT, "RIGHT": e.KEY_RIGHT,
        "A": e.KEY_LEFTCTRL, "B": e.KEY_SPACE, "X": e.KEY_LEFTSHIFT, "Y": e.KEY_ENTER,
        "START": e.KEY_ESC, "SELECT": e.KEY_Y, "L": e.KEY_COMMA, "R": e.KEY_DOT,
    },
}


def main():
    profile = sys.argv[1] if len(sys.argv) > 1 else "doom"
    keymap = PROFILES.get(profile, PROFILES["doom"])

    cfg = json.loads(BUTTONS.read_text())
    pins = {a: int(p) for a, p in cfg["pins"].items()
            if int(p) >= 0 and a in keymap}
    pressed_level = 0 if cfg.get("active_low", True) else 1

    ui = UInput({e.EV_KEY: sorted(set(keymap.values()))}, name="neobox-gamepad")

    settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP)
    req = gpiod.request_lines("/dev/gpiochip0", consumer="neobox-keybridge",
                              config={p: settings for p in pins.values()})
    plist = sorted(pins.values())
    action_of = {p: a for a, p in pins.items()}

    run = {"v": True}
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: run.update(v=False))

    prev = {p: 1 for p in plist}
    while run["v"]:
        vals = req.get_values()
        for i, p in enumerate(plist):
            lvl = 1 if vals[i] == Value.ACTIVE else 0
            if lvl != prev[p]:
                ui.write(e.EV_KEY, keymap[action_of[p]],
                         1 if lvl == pressed_level else 0)
                ui.syn()
                prev[p] = lvl
        time.sleep(0.008)
    try:
        ui.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
