"""Generic modal list menu — used for the MENU overlay and the power menu."""
from __future__ import annotations

import pygame

from . import Screen
from .. import config


class ListMenu(Screen):
    modal = True     # handles MENU/EXIT itself instead of the global router
    overlay = True   # draw the screen beneath as a dim backdrop

    def __init__(self, app, title: str, items: list[tuple[str, object]]):
        super().__init__(app)
        self.title = title
        self.items = items          # list of (label, callback)
        self.index = 0

    def on_action(self, action: str):
        if action in ("UP",):
            self.index = (self.index - 1) % len(self.items)
        elif action in ("DOWN",):
            self.index = (self.index + 1) % len(self.items)
        elif action == "A":
            label, cb = self.items[self.index]
            self.app.pop()          # close the menu first
            if callable(cb):
                cb()
        elif action in ("B", "MENU", "EXIT"):
            self.app.pop()

    def draw(self, surf, theme):
        from ..ui import panel
        panel.dim_backdrop(surf, alpha=150)

        w = 240
        row_h = 32
        h = 24 + len(self.items) * row_h + 12
        box = pygame.Rect(0, 0, w, h)
        box.center = (config.SCREEN_W // 2, config.SCREEN_H // 2)
        panel.card(surf, theme, box, title=self.title)

        font = theme.font("ui")
        y = box.y + 16
        for i, (label, _) in enumerate(self.items):
            row = pygame.Rect(box.x + 10, y, box.width - 20, row_h - 4)
            sel = (i == self.index)
            if sel:
                pygame.draw.rect(surf, theme.color("tile_sel"), row, border_radius=6)
                pygame.draw.rect(surf, theme.color("accent"), row, width=1, border_radius=6)
            label_surf = font.render(label, True,
                                     theme.color("accent") if sel else theme.color("text"))
            surf.blit(label_surf, (row.x + 12, row.centery - label_surf.get_height() // 2))
            y += row_h

    def hints(self):
        return [("↑↓", "move"), ("A", "select"), ("B", "close")]
