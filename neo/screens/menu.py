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
        overlay = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surf.blit(overlay, (0, 0))

        w, pad = 240, 10
        row_h = 30
        h = 44 + len(self.items) * row_h
        box = pygame.Rect(0, 0, w, h)
        box.center = (config.SCREEN_W // 2, config.SCREEN_H // 2)
        pygame.draw.rect(surf, theme.color("bg_alt"), box, border_radius=12)
        pygame.draw.rect(surf, theme.color("accent"), box, width=2, border_radius=12)

        title = theme.font("ui", bold=True).render(self.title, True, theme.color("accent"))
        surf.blit(title, (box.x + pad, box.y + 10))
        font = theme.font("ui")
        y = box.y + 40
        for i, (label, _) in enumerate(self.items):
            row = pygame.Rect(box.x + 6, y, box.width - 12, row_h - 4)
            if i == self.index:
                pygame.draw.rect(surf, theme.color("tile_sel"), row, border_radius=6)
                pygame.draw.rect(surf, theme.color("accent"), row, width=1, border_radius=6)
            surf.blit(font.render(label, True, theme.color("text")),
                      (row.x + 8, row.y + row_h // 2 - font.get_height() // 2 - 2))
            y += row_h

    def hints(self):
        return [("↑↓", "move"), ("A", "select"), ("B", "close")]
