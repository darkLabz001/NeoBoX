#!/usr/bin/env python3
"""Snapshot the level of every header GPIO (BCM 2-27) with pull-up bias.

Run once at rest and again while holding a button; diff the two to find the
button's pin. Prints "BCM:level" pairs and flags any line low at rest.
"""
from __future__ import annotations

import gpiod
from gpiod.line import Bias, Direction, Value

LINES = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]


def main():
    settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP)
    req = gpiod.request_lines("/dev/gpiochip0", consumer="neo-levels",
                              config={l: settings for l in LINES})
    vals = req.get_values()
    req.release()
    out = {LINES[i]: (1 if vals[i] == Value.ACTIVE else 0) for i in range(len(LINES))}
    print(" ".join(f"{p}:{v}" for p, v in out.items()))
    low = [p for p, v in out.items() if v == 0]
    print("LOW_AT_READ:", low)


if __name__ == "__main__":
    main()
