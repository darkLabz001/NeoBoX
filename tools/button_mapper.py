#!/usr/bin/env python3
"""Interactive GPIO button mapper for the Waveshare Game HAT.

Run this ON THE PI (over `ssh -t`). It watches the user GPIO lines (BCM 2..27),
asks you to press each button one at a time, records which line goes active-low,
and writes the verified pin map to config/buttons.json.

    ssh -t kali@<pi> 'cd ~/neo && python3 tools/button_mapper.py'
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

CANDIDATES = list(range(2, 28))   # BCM GPIOs broken out on the 40-pin header
ACTIONS = ["UP", "DOWN", "LEFT", "RIGHT", "A", "B", "X", "Y",
           "START", "SELECT", "L", "R", "MENU", "EXIT"]
OUT = Path(__file__).resolve().parent.parent / "config" / "buttons.json"


def open_lines():
    import gpiod
    chip_name = "gpiochip0"
    try:  # gpiod v2
        from gpiod.line import Direction, Bias
        chip = gpiod.Chip(chip_name)
        settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP)
        req = chip.request_lines(consumer="neo-mapper",
                                 config={p: settings for p in CANDIDATES})

        def read():
            vals = req.get_values()
            return {CANDIDATES[i]: int(vals[i]) for i in range(len(CANDIDATES))}
        return read
    except Exception:  # gpiod v1
        chip = gpiod.Chip(chip_name)
        lines = {}
        for p in CANDIDATES:
            ln = chip.get_line(p)
            ln.request(consumer="neo-mapper", type=gpiod.LINE_REQ_DIR_IN,
                       flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP)
            lines[p] = ln

        def read():
            return {p: ln.get_value() for p, ln in lines.items()}
        return read


def wait_for_press(read, baseline, mapped):
    """Return the pin that went low (pressed). Ignore already-mapped pins."""
    while True:
        cur = read()
        for pin, level in cur.items():
            if pin in mapped:
                continue
            if baseline.get(pin, 1) == 1 and level == 0:
                # debounce
                time.sleep(0.03)
                if read().get(pin) == 0:
                    return pin
        time.sleep(0.005)


def wait_for_release(read, pin):
    while read().get(pin) == 0:
        time.sleep(0.01)
    time.sleep(0.05)


def main():
    try:
        read = open_lines()
    except Exception as exc:
        print(f"Could not open GPIO ({exc}). Run on the Pi with libgpiod installed.")
        sys.exit(1)

    baseline = read()
    active_at_rest = [p for p, v in baseline.items() if v == 0]
    if active_at_rest:
        print(f"Note: pins low at rest (ignored as candidates): {active_at_rest}")

    print("\n=== Neo button mapper ===")
    print("Press each button when prompted. Ctrl-C to abort.\n")
    pins: dict[str, int] = {}
    mapped: set[int] = set(active_at_rest)
    for action in ACTIONS:
        try:
            input(f"  Press [{action}] then Enter to skip if it doesn't exist… ")
        except EOFError:
            pass
        # Give a short window to detect the press that may have happened.
        pin = None
        deadline = time.time() + 0.4
        while time.time() < deadline:
            cur = read()
            for p, level in cur.items():
                if p not in mapped and baseline.get(p, 1) == 1 and level == 0:
                    pin = p
                    break
            if pin is not None:
                break
            time.sleep(0.005)
        if pin is None:
            print(f"    {action}: (skipped / not detected)")
            pins[action] = -1
            continue
        wait_for_release(read, pin)
        pins[action] = pin
        mapped.add(pin)
        print(f"    {action} -> BCM {pin}")

    data = {
        "_comment": "Verified by tools/button_mapper.py",
        "chip": "gpiochip0",
        "active_low": True,
        "pins": pins,
    }
    OUT.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\nWrote {OUT}\n{json.dumps(pins, indent=2)}")


if __name__ == "__main__":
    main()
