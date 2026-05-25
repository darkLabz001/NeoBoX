"""Input abstraction.

Logical actions are decoupled from physical sources so the same UI code runs
from a keyboard (development on HDMI) or the Game HAT's GPIO buttons.

Actions: UP DOWN LEFT RIGHT A B X Y START SELECT L R MENU EXIT

MENU and EXIT are not on the Pi's GPIO on this HAT, so they're synthesised as
chords (e.g. L+R, START+SELECT) defined in config/buttons.json.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable, Optional

import pygame

ACTIONS = [
    "UP", "DOWN", "LEFT", "RIGHT",
    "A", "B", "X", "Y",
    "START", "SELECT", "L", "R",
    "MENU", "EXIT",
]

DEFAULT_KEYMAP = {
    pygame.K_UP: "UP",
    pygame.K_DOWN: "DOWN",
    pygame.K_LEFT: "LEFT",
    pygame.K_RIGHT: "RIGHT",
    pygame.K_w: "UP",
    pygame.K_s: "DOWN",
    pygame.K_a: "LEFT",
    pygame.K_d: "RIGHT",
    pygame.K_j: "A",
    pygame.K_RETURN: "A",
    pygame.K_k: "B",
    pygame.K_ESCAPE: "B",
    pygame.K_u: "X",
    pygame.K_i: "Y",
    pygame.K_q: "L",
    pygame.K_e: "R",
    pygame.K_1: "SELECT",
    pygame.K_2: "START",
    pygame.K_m: "MENU",
    pygame.K_BACKSPACE: "EXIT",
}


class KeyboardBackend:
    """Translates pygame KEYDOWN events into logical actions."""

    def __init__(self, keymap: Optional[dict] = None):
        self.keymap = keymap or DEFAULT_KEYMAP
        pygame.key.set_repeat(300, 110)

    def actions_from_event(self, event) -> list[str]:
        if event.type == pygame.KEYDOWN and event.key in self.keymap:
            return [self.keymap[event.key]]
        return []


class GpioBackend:
    """Poll the Game HAT buttons from GPIO with pull-up; emit logical actions.

    Polling (not edge events) proved reliable on this hardware. Single buttons
    fire immediately; the buttons that participate in a chord are held back by a
    short coalesce window so a simultaneous press becomes MENU/EXIT instead.
    """

    def __init__(self, config_path, on_press: Callable[[str], None], poll_hz: int = 120):
        self.on_press = on_press
        self.poll_interval = 1.0 / poll_hz
        self.coalesce = 0.06
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        with open(config_path) as fh:
            cfg = json.load(fh)
        self.chip_path = "/dev/" + cfg.get("chip", "gpiochip0")
        self.active_low = cfg.get("active_low", True)
        # action -> pin (skip unmapped -1)
        self.pin_of = {a: int(p) for a, p in cfg.get("pins", {}).items()
                       if p is not None and int(p) >= 0}
        self.action_of = {p: a for a, p in self.pin_of.items()}
        # combos: action -> [member action names]
        self.combos = []
        combo_pins = set()
        for caction, members in cfg.get("combos", {}).items():
            pins = {self.pin_of[m] for m in members if m in self.pin_of}
            if len(pins) == len(members):
                self.combos.append((caction, frozenset(pins)))
                combo_pins |= pins
        self.combo_pins = combo_pins

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self):
        try:
            import gpiod
            from gpiod.line import Bias, Direction, Value
        except Exception as exc:  # pragma: no cover - device only
            print(f"[gpio] libgpiod unavailable: {exc}")
            return

        pins = sorted(self.pin_of.values())
        settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP)
        # Retry: after a game exits, the key bridge may still be releasing the
        # lines for a moment. Without this, resume after a game could silently
        # leave the UI with no buttons.
        req = None
        for attempt in range(15):
            try:
                req = gpiod.request_lines(self.chip_path, consumer="neo-ui",
                                          config={p: settings for p in pins})
                break
            except Exception as exc:  # pragma: no cover
                if self._stop.is_set():
                    return
                if attempt == 0 or attempt == 14:
                    print(f"[gpio] request lines busy (try {attempt}): {exc}")
                time.sleep(0.1)
        if req is None:
            print("[gpio] cannot request lines after retries")
            return

        pressed_level = 0 if self.active_low else 1

        def read_down() -> set:
            vals = req.get_values()
            down = set()
            for i, p in enumerate(pins):
                level = 1 if vals[i] == Value.ACTIVE else 0
                if level == pressed_level:
                    down.add(p)
            return down

        prev_down: set = set()
        pending: dict = {}          # combo pin -> time it went down
        active_combo: dict = {c: False for c, _ in self.combos}

        while not self._stop.is_set():
            try:
                down = read_down()
            except Exception as exc:  # pragma: no cover
                print(f"[gpio] read error: {exc}")
                break
            now = time.monotonic()

            for pin in down - prev_down:               # newly pressed
                if pin in self.combo_pins:
                    pending[pin] = now
                else:
                    self.on_press(self.action_of[pin])

            for caction, cpins in self.combos:          # chord formed?
                if cpins <= down and not active_combo[caction]:
                    active_combo[caction] = True
                    self.on_press(caction)
                    for p in cpins:
                        pending.pop(p, None)            # suppress the singles
                elif not (cpins <= down):
                    active_combo[caction] = False

            for pin, t in list(pending.items()):        # coalesce timeout -> single
                if pin not in down:
                    pending.pop(pin, None)
                elif now - t >= self.coalesce:
                    self.on_press(self.action_of[pin])
                    pending.pop(pin, None)

            prev_down = down
            time.sleep(self.poll_interval)

        # Release the lines promptly so a game's keybridge can claim them.
        try:
            req.release()
        except Exception:
            pass
