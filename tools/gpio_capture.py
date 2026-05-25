#!/usr/bin/env python3
"""Capture button presses in order, to build the GPIO pin map.

Watches the header GPIOs (BCM, excluding UART 14/15 and EEPROM 0/1) for
falling edges with pull-up bias. Records each NEW pin the first time it goes
low. Prints progress live and writes the ordered pin list to a JSON file.

    python3 tools/gpio_capture.py <seconds> <out.json> [expected_count]
"""
from __future__ import annotations

import datetime
import json
import sys
import time

import gpiod
from gpiod.line import Bias, Direction, Edge

# Candidate header GPIOs; skip 0/1 (EEPROM) and 14/15 (UART console).
CANDIDATES = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17, 18, 19, 20, 21,
              22, 23, 24, 25, 26, 27, 2, 3]


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 150
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/neo_btn_order.json"
    expected = int(sys.argv[3]) if len(sys.argv) > 3 else 14

    settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        bias=Bias.PULL_UP,
        edge_detection=Edge.FALLING,
        debounce_period=datetime.timedelta(milliseconds=15),
    )
    try:
        req = gpiod.request_lines(
            "/dev/gpiochip0", consumer="neo-capture",
            config={p: settings for p in CANDIDATES},
        )
    except Exception as exc:
        print(f"ERROR requesting GPIO lines: {exc}", flush=True)
        sys.exit(1)

    order: list[int] = []
    seen: set[int] = set()
    start = time.time()
    print(f"capturing for up to {seconds:.0f}s — press buttons one at a time...", flush=True)
    try:
        while time.time() - start < seconds and len(order) < expected:
            if req.wait_edge_events(timeout=datetime.timedelta(milliseconds=400)):
                for ev in req.read_edge_events():
                    pin = ev.line_offset
                    if pin not in seen:
                        seen.add(pin)
                        order.append(pin)
                        print(f"  #{len(order):2d}  BCM {pin}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        req.release()

    with open(out, "w") as fh:
        json.dump(order, fh)
    print(f"\nCAPTURED {len(order)} pins in order: {order}", flush=True)
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
