"""On-screen keyboard, navigable by the D-pad — for entering targets/inputs."""
from __future__ import annotations

import pygame

from . import Screen
from .. import config
from ..ui import statusbar

ROWS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl-"),
    list("zxcvbnm.:/"),
    ["SHIFT", "SPACE", "DEL", "DONE"],
]


class OnScreenKeyboard(Screen):
    modal = True

    def __init__(self, app, prompt: str, on_done, initial: str = ""):
        super().__init__(app)
        self.title = prompt
        self.prompt = prompt
        self.on_done = on_done
        self.value = initial
        self.shift = False
        self.row = 1
        self.col = 0

    def _key(self, r, c):
        row = ROWS[r]
        return row[min(c, len(row) - 1)]

    def on_action(self, action: str):
        if action in ("UP", "DOWN", "LEFT", "RIGHT"):
            if action == "UP":
                self.row = (self.row - 1) % len(ROWS)
            elif action == "DOWN":
                self.row = (self.row + 1) % len(ROWS)
            elif action == "LEFT":
                self.col -= 1
            elif action == "RIGHT":
                self.col += 1
            self.col %= len(ROWS[self.row])
        elif action == "A":
            self._press(self._key(self.row, self.col))
        elif action == "B":
            self.value = self.value[:-1]
        elif action == "X":
            self.shift = not self.shift
        elif action == "START":
            self._finish()
        elif action in ("MENU", "EXIT"):
            self.app.pop()

    def _press(self, key):
        if key == "SHIFT":
            self.shift = not self.shift
        elif key == "SPACE":
            self.value += " "
        elif key == "DEL":
            self.value = self.value[:-1]
        elif key == "DONE":
            self._finish()
        else:
            self.value += key.upper() if self.shift else key

    def _finish(self):
        self.on_done(self.value)

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "INPUT")
        font = theme.font("ui")
        small = theme.font("small")

        # prompt + current value
        surf.blit(small.render(self.prompt, True, theme.color("text_dim")),
                  (10, statusbar.HEIGHT + 8))
        box = pygame.Rect(10, statusbar.HEIGHT + 24, config.SCREEN_W - 20, 24)
        pygame.draw.rect(surf, theme.color("tile"), box, border_radius=6)
        pygame.draw.rect(surf, theme.color("accent"), box, width=1, border_radius=6)
        cursor = "_" if (pygame.time.get_ticks() // 400) % 2 else " "
        surf.blit(font.render(self.value + cursor, True, theme.color("text")),
                  (box.x + 6, box.y + 4))

        # keyboard grid
        gy = statusbar.HEIGHT + 58
        kh = 26
        gap = 4
        for r, row in enumerate(ROWS):
            n = len(row)
            kw = (config.SCREEN_W - 20 - (n - 1) * gap) // n
            for c, key in enumerate(row):
                rect = pygame.Rect(10 + c * (kw + gap), gy + r * (kh + gap), kw, kh)
                sel = (r == self.row and c == self.col)
                bg = theme.color("tile_sel") if sel else theme.color("tile")
                pygame.draw.rect(surf, bg, rect, border_radius=5)
                if sel:
                    pygame.draw.rect(surf, theme.color("accent"), rect, width=2, border_radius=5)
                label = key
                if key not in ("SHIFT", "SPACE", "DEL", "DONE"):
                    label = key.upper() if self.shift else key
                lab = small.render(label if len(label) <= 5 else label[:5], True,
                                   theme.color("text"))
                surf.blit(lab, lab.get_rect(center=rect.center))

    def hints(self):
        return [("A", "type"), ("X", "shift"), ("B", "del"), ("Start", "done")]
