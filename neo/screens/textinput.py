"""On-screen keyboard, navigable by the D-pad. Lowercase / UPPERCASE / symbols
layers (SHIFT toggles case, SYM/ABC switch layers) so passwords with any symbol
can be typed."""
from __future__ import annotations

import pygame

from . import Screen
from .. import config
from ..ui import statusbar

SPECIAL = {"SHIFT", "SYM", "ABC", "SPACE", "DEL", "DONE"}

LOWER = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
    ["SHIFT", "SYM", "SPACE", "DEL", "DONE"],
]
UPPER = [
    list("1234567890"),
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
    ["SHIFT", "SYM", "SPACE", "DEL", "DONE"],
]
SYMBOLS = [
    list("1234567890"),
    ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"],
    ["-", "_", "=", "+", "[", "]", "{", "}", ":", ";"],
    ["'", '"', "`", "~", "<", ">", ",", ".", "/", "?"],
    ["ABC", "\\", "|", "SPACE", "DEL", "DONE"],
]
LAYOUTS = {"lower": LOWER, "upper": UPPER, "sym": SYMBOLS}


class OnScreenKeyboard(Screen):
    modal = True

    def __init__(self, app, prompt: str, on_done, initial: str = ""):
        super().__init__(app)
        self.title = prompt
        self.prompt = prompt
        self.on_done = on_done
        self.value = initial
        self.mode = "lower"
        self.row = 1
        self.col = 0

    @property
    def rows(self):
        return LAYOUTS[self.mode]

    def _clamp(self):
        self.row = max(0, min(self.row, len(self.rows) - 1))
        self.col = max(0, min(self.col, len(self.rows[self.row]) - 1))

    def _key(self):
        return self.rows[self.row][self.col]

    def on_action(self, action: str):
        if action == "UP":
            self.row = (self.row - 1) % len(self.rows)
        elif action == "DOWN":
            self.row = (self.row + 1) % len(self.rows)
        elif action == "LEFT":
            self.col = (self.col - 1) % len(self.rows[self.row])
        elif action == "RIGHT":
            self.col = (self.col + 1) % len(self.rows[self.row])
        elif action == "A":
            self._press(self._key())
        elif action == "B":
            self.value = self.value[:-1]
        elif action == "X":                       # quick case toggle
            self.mode = "upper" if self.mode == "lower" else "lower"
        elif action in ("L", "R"):                # quick jump to symbols/back
            self.mode = "sym" if self.mode != "sym" else "lower"
        elif action == "START":
            self._finish()
        elif action in ("MENU", "EXIT"):
            self.app.pop()
        self._clamp()

    def _press(self, key):
        if key == "SHIFT":
            self.mode = "upper" if self.mode == "lower" else "lower"
        elif key == "SYM":
            self.mode = "sym"
        elif key == "ABC":
            self.mode = "lower"
        elif key == "SPACE":
            self.value += " "
        elif key == "DEL":
            self.value = self.value[:-1]
        elif key == "DONE":
            self._finish()
        else:
            self.value += key

    def _finish(self):
        self.on_done(self.value)

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "INPUT")
        font = theme.font("ui")
        small = theme.font("small")

        surf.blit(small.render(self.prompt[:48], True, theme.color("text_dim")),
                  (10, statusbar.HEIGHT + 6))
        box = pygame.Rect(10, statusbar.HEIGHT + 22, config.SCREEN_W - 20, 22)
        pygame.draw.rect(surf, theme.color("tile"), box, border_radius=6)
        pygame.draw.rect(surf, theme.color("accent"), box, width=1, border_radius=6)
        cursor = "_" if (pygame.time.get_ticks() // 400) % 2 else " "
        text = self.value + cursor
        tsurf = font.render(text, True, theme.color("text"))
        # right-align (show the end) if the value overflows the box
        prev = surf.get_clip()
        surf.set_clip(box.inflate(-8, 0))
        x = box.x + 6
        if tsurf.get_width() > box.width - 12:
            x = box.right - 6 - tsurf.get_width()
        surf.blit(tsurf, (x, box.y + 3))
        surf.set_clip(prev)

        gy = statusbar.HEIGHT + 52
        kh = 24
        gap = 4
        for r, row in enumerate(self.rows):
            n = len(row)
            kw = (config.SCREEN_W - 20 - (n - 1) * gap) // n
            for c, key in enumerate(row):
                rect = pygame.Rect(10 + c * (kw + gap), gy + r * (kh + gap), kw, kh)
                sel = (r == self.row and c == self.col)
                pygame.draw.rect(surf, theme.color("tile_sel") if sel else theme.color("tile"),
                                 rect, border_radius=5)
                if sel:
                    pygame.draw.rect(surf, theme.color("accent"), rect, width=2, border_radius=5)
                label = key if key in SPECIAL else key
                lab = small.render(label[:5], True, theme.color("text"))
                surf.blit(lab, lab.get_rect(center=rect.center))

    def is_animating(self):
        return True   # blinking cursor

    def hints(self):
        return [("A", "type"), ("X", "case"), ("L/R", "sym"), ("B", "del"), ("Start", "ok")]
