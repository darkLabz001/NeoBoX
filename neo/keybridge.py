#!/usr/bin/env python3
"""GPIO -> uinput keyboard bridge so the HAT buttons drive external games.

Run as root (needs /dev/uinput).  Usage:  keybridge.py [profile]
NeoBoX releases its own GPIO hold before starting this, and kills it after the
game exits. Reads the verified pin map from config/buttons.json.

DOOM controls:
  Joystick = move: up/down forward/back, left/right STRAFE
  L/R = turn left/right    A = fire(Ctrl)   B = use(Space)   X = run(Shift)
  Start = menu(Esc)   Select = select(Enter)   Y = 'y' (confirm prompts)
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
        "UP": e.KEY_UP, "DOWN": e.KEY_DOWN,         # forward / back
        "LEFT": e.KEY_COMMA, "RIGHT": e.KEY_DOT,    # strafe left / right
        "L": e.KEY_LEFT, "R": e.KEY_RIGHT,          # turn left / right
        "A": e.KEY_LEFTCTRL, "B": e.KEY_SPACE, "X": e.KEY_LEFTSHIFT,
        "Y": e.KEY_Y,                               # 'y' for prompts
        "START": e.KEY_ESC, "SELECT": e.KEY_ENTER,  # menu / select
    },
    "retroarch": {
        "UP": e.KEY_UP, "DOWN": e.KEY_DOWN,
        "LEFT": e.KEY_LEFT, "RIGHT": e.KEY_RIGHT,
        "A": e.KEY_X, "B": e.KEY_Z, "X": e.KEY_S, "Y": e.KEY_A,
        "L": e.KEY_Q, "R": e.KEY_W,
        "START": e.KEY_ENTER, "SELECT": e.KEY_RSHIFT,
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

    ui = UInput({e.EV_KEY: sorted(set(keymap.values()))}, name="neobox-gamepad")

    # Request lines in the SAME order we index get_values(), or buttons scramble.
    plist = sorted(pins.values())
    settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP)
    req = gpiod.request_lines(chip_path, consumer="neobox-keybridge",
                              config={p: settings for p in plist})
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
