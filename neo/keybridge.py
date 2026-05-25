#!/usr/bin/env python3
"""GPIO -> uinput keyboard bridge so the HAT buttons drive external games.
Run as root (needs /dev/uinput). Usage: keybridge.py [profile]

Logs to <repo>/keybridge.log so input problems can be diagnosed without SSH
(view it in the Web UI). Retries acquiring the GPIO lines in case NeoBoX is
still releasing them.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

import gpiod
from gpiod.line import Bias, Direction, Value
from evdev import UInput, ecodes as e

REPO = Path(__file__).resolve().parent.parent
BUTTONS = REPO / "config" / "buttons.json"
LOG = REPO / "keybridge.log"

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
        "START": e.KEY_ENTER, "SELECT": e.KEY_RIGHTSHIFT,
    },
    "mpv": {
        "UP": e.KEY_VOLUMEUP, "DOWN": e.KEY_VOLUMEDOWN,
        "LEFT": e.KEY_LEFT, "RIGHT": e.KEY_RIGHT,
        "A": e.KEY_SPACE, "B": e.KEY_Q,
        "X": e.KEY_M, "Y": e.KEY_I,
        "L": e.KEY_9, "R": e.KEY_0,
        "START": e.KEY_P, "SELECT": e.KEY_O,
    },
}
PROFILES["ps1"] = PROFILES["retroarch"]   # PS1 runs in RetroArch (pcsx-rearmed)


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def main():
    profile = sys.argv[1] if len(sys.argv) > 1 else "doom"
    keymap = PROFILES.get(profile, PROFILES["doom"])

    cfg = json.loads(BUTTONS.read_text())
    chip_path = "/dev/" + cfg.get("chip", "gpiochip0")
    pins = {a: int(p) for a, p in cfg["pins"].items()
            if int(p) >= 0 and a in keymap}
    pressed_level = 0 if cfg.get("active_low", True) else 1
    plist = sorted(pins.values())
    action_of = {p: a for a, p in pins.items()}

    log(f"=== keybridge start: profile={profile} pins={pins} chip={chip_path} ===")

    try:
        ui = UInput({e.EV_KEY: sorted(set(keymap.values()))}, name="neobox-keypad")
        log("uinput keyboard created OK")
    except Exception as exc:
        log(f"FATAL: uinput create failed: {exc}")
        return

    # Acquire GPIO lines, retrying while NeoBoX finishes releasing them.
    settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP)
    req = None
    for attempt in range(40):
        try:
            req = gpiod.request_lines(chip_path, consumer="neobox-keybridge",
                                      config={p: settings for p in plist})
            log(f"GPIO lines acquired on attempt {attempt}")
            break
        except Exception as exc:
            if attempt % 10 == 0:
                log(f"GPIO busy, retrying ({attempt}): {exc}")
            time.sleep(0.1)
    if req is None:
        log("FATAL: could not acquire GPIO lines after retries")
        ui.close()
        return

    run = {"v": True}
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: run.update(v=False))

    panic_pins = {pins[a] for a in ("START", "SELECT", "L", "R") if a in pins}
    panic_hold = 0
    presses = 0

    prev = {p: 1 for p in plist}
    log("entering poll loop — press buttons now")
    while run["v"]:
        vals = req.get_values()
        pressed = set()
        for i, p in enumerate(plist):
            lvl = 1 if vals[i] == Value.ACTIVE else 0
            if lvl == pressed_level:
                pressed.add(p)
            if lvl != prev[p]:
                down = lvl == pressed_level
                ui.write(e.EV_KEY, keymap[action_of[p]], 1 if down else 0)
                ui.syn()
                if down:
                    presses += 1
                    if presses <= 60:
                        log(f"  press {action_of[p]} (BCM {p}) -> key {keymap[action_of[p]]}")
                prev[p] = lvl
        if panic_pins and panic_pins <= pressed:
            panic_hold += 1
            if panic_hold > 40:   # ~0.3s held
                log("PANIC combo -> killing game")
                os.system("pkill -9 -f 'retroarch|chocolate-doom|mednafen|pcsx|mpv'")
                break
        else:
            panic_hold = 0
        time.sleep(0.008)
    log(f"keybridge exit ({presses} presses seen)")
    try:
        req.release()
    except Exception:
        pass
    ui.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"FATAL: {exc}")
        raise
