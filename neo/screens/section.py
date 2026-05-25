"""Section screen: the payloads inside a section (or builtin Settings actions)."""
from __future__ import annotations

import pygame

from . import Screen
from .. import config, payloads
from ..ui import statusbar
from ..ui.grid import IconGrid


class SectionScreen(Screen):
    def __init__(self, app, section: dict):
        super().__init__(app)
        self.section = section
        self.title = section["name"]
        self.items: list[dict] = []
        if section.get("builtin"):
            self._build_settings()
        else:
            self._build_payloads()
        area = pygame.Rect(0, statusbar.HEIGHT + 2, config.SCREEN_W,
                           config.SCREEN_H - statusbar.HEIGHT - 2 - 24)
        self.grid = IconGrid(self.items, area, cols=3, rows=2) if self.items else None
        self.empty_msg = None if self.items else \
            f"No payloads yet.\nAdd a .py to payloads/{section['id']}/"

    def _build_payloads(self):
        for p in payloads.list_payloads(self.section["id"]):
            item = {"name": p["name"], "glyph": p["name"][:1].upper(), "_payload": p}
            icon = p.get("icon")
            if icon and (config.ICONS_DIR / f"{icon}.png").exists():
                item["image"] = icon
            self.items.append(item)

    def _build_settings(self):
        self.items = [
            {"name": "Theme", "glyph": "◑", "_action": "theme"},
            {"name": "Update", "glyph": "↡", "_action": "update"},
            {"name": "About", "glyph": "i", "_action": "about"},
            {"name": "Power", "glyph": "⏻", "_action": "power"},
        ]

    def on_action(self, action: str):
        if self.grid and action in ("UP", "DOWN", "LEFT", "RIGHT"):
            d = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}[action]
            self.grid.move(*d)
        elif self.grid and action == "L":
            self.grid.page_jump(-1)
        elif self.grid and action == "R":
            self.grid.page_jump(1)
        elif action == "B":
            self.app.pop()
        elif action == "A" and self.grid:
            sel = self.grid.selected()
            if not sel:
                return
            if "_payload" in sel:
                self.app.run_payload(sel["_payload"])
            elif "_action" in sel:
                self.app.settings_action(sel["_action"])

    def update(self, dt: float):
        if self.grid:
            self.grid.update(dt)

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        if self.grid:
            self.grid.draw(surf, theme)
        else:
            font = theme.font("ui")
            y = config.SCREEN_H // 2 - 16
            for line in self.empty_msg.split("\n"):
                t = font.render(line, True, theme.color("text_dim"))
                surf.blit(t, t.get_rect(center=(config.SCREEN_W // 2, y)))
                y += font.get_height() + 4
        self.app.statusbar.draw(surf, theme, self.title)
