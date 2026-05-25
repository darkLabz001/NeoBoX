"""Home screen: NeoBoX background + scrollable pages of section icons."""
from __future__ import annotations

import json

import pygame

from . import Screen
from .section import SectionScreen
from .. import config
from ..ui import statusbar
from ..ui.grid import IconGrid


class HomeScreen(Screen):
    title = "NEOBOX"

    def __init__(self, app):
        super().__init__(app)
        with open(config.SECTIONS_FILE) as fh:
            self.sections = json.load(fh)["sections"]
        # Section icons already include their label, so hide the text label.
        items = [
            {"name": s["name"], "image": s.get("icon", s["id"]),
             "hide_label": True, "_section": s}
            for s in self.sections
        ]
        area = pygame.Rect(0, statusbar.HEIGHT, config.SCREEN_W,
                           config.SCREEN_H - statusbar.HEIGHT - 24)
        self.grid = IconGrid(items, area, cols=3, rows=2, margin=14, gap=12)

    def on_action(self, action: str):
        if action in ("UP", "DOWN", "LEFT", "RIGHT"):
            d = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}[action]
            self.grid.move(*d)
        elif action == "L":
            self.grid.page_jump(-1)
        elif action == "R":
            self.grid.page_jump(1)
        elif action == "A":
            section = self.sections[self.grid.index]
            self.app.push(SectionScreen(self.app, section))

    def update(self, dt: float):
        self.grid.update(dt)

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.grid.draw(surf, theme)
        # transparent status: show clock/wifi but keep the NeoBoX logo visible
        self.app.statusbar.draw(surf, theme, self.title, transparent=True)
