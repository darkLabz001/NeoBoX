#!/usr/bin/env python3
"""Capture button presses by polling pin LEVELS (not edge events).

More robust than edge detection: requests BCM 2-27 with pull-up, samples every
few ms, and records each line the first time it drops 1->0. Hold each button
~1-2s. Prints live and writes the ordered pin list.

    python3 tools/gpio_capture_poll.py <seconds> <out.json> [expected]
"""
from __future__ import annotations

import json
import sys
import time

import gpiod
from gpiod.line import Bias, Direction, Value

LINES = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17, 18, 19, 20, 21,
         22, 23, 24, 25, 26, 27, 2, 3]


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 240
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/neo_btn_order.json"
    expected = int(sys.argv[3]) if len(sys.argv) > 3 else 14

    settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP)
    req = gpiod.request_lines("/dev/gpiochip0", consumer="neo-poll",
                              config={l: settings for l in LINES})

    def read():
        vals = req.get_values()
        return {LINES[i]: (1 if vals[i] == Value.ACTIVE else 0) for i in range(len(LINES))}

    base = read()
    print(f"baseline (low pins ignored): {[p for p,v in base.items() if v==0]}", flush=True)
    print(f"polling {seconds:.0f}s — press & HOLD each button ~2s, in order...", flush=True)

    order: list[int] = []
    seen = {p for p, v in base.items() if v == 0}   # ignore stuck-low
    start = time.time()
    while time.time() - start < seconds and len(order) < expected:
        cur = read()
        for pin, level in cur.items():
            if level == 0 and pin not in seen:
                # debounce: confirm still low a moment later
                time.sleep(0.02)
                if read().get(pin) == 0:
                    seen.add(pin)
                    order.append(pin)
                    print(f"  #{len(order):2d}  BCM {pin}", flush=True)
        time.sleep(0.005)

    req.release()
    with open(out, "w") as fh:
        json.dump(order, fh)
    print(f"\nCAPTURED {len(order)}: {order}", flush=True)


if __name__ == "__main__":
    main()
