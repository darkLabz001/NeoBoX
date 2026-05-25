#!/usr/bin/env python3
"""Live GPIO diagnostic: print ANY edge on either chip, to confirm wiring.

Watches gpiochip0 (BCM 2-13,16-27 with pull-up) and gpiochip1 (exp-gpio 0-7)
for both rising and falling edges, printing each event as it happens.

    python3 tools/gpio_diag.py [seconds]
"""
from __future__ import annotations

import datetime
import sys
import time

import gpiod
from gpiod.line import Bias, Direction, Edge

CHIP0 = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]
CHIP1 = [0, 1, 2, 3, 4, 5, 6, 7]


def make_req(path, lines, bias):
    settings = gpiod.LineSettings(
        direction=Direction.INPUT, bias=bias, edge_detection=Edge.BOTH,
        debounce_period=datetime.timedelta(milliseconds=8),
    )
    try:
        return gpiod.request_lines(path, consumer="neo-diag",
                                   config={l: settings for l in lines})
    except Exception as exc:
        print(f"  ({path}: could not request {lines}: {exc})", flush=True)
        return None


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 90
    reqs = []
    r0 = make_req("/dev/gpiochip0", CHIP0, Bias.PULL_UP)
    if r0:
        reqs.append(("chip0", r0))
    r1 = make_req("/dev/gpiochip1", CHIP1, Bias.AS_IS)
    if r1:
        reqs.append(("chip1", r1))
    if not reqs:
        print("No GPIO chips available", flush=True)
        sys.exit(1)

    print(f"watching for {seconds:.0f}s — press ANY button now...", flush=True)
    start = time.time()
    count = 0
    while time.time() - start < seconds:
        for name, req in reqs:
            if req.wait_edge_events(timeout=datetime.timedelta(milliseconds=100)):
                for ev in req.read_edge_events():
                    edge = "FALL" if ev.event_type == ev.Type.FALLING_EDGE else "rise"
                    count += 1
                    print(f"  {name} BCM {ev.line_offset:>2}  {edge}", flush=True)
    print(f"done — {count} edges seen", flush=True)


if __name__ == "__main__":
    main()
