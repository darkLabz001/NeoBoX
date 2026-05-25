"""Screen stack: each screen handles actions, updates, and draws itself."""
from __future__ import annotations

import pygame


class Screen:
    title = "NEO"
    modal = False    # if True, the screen handles MENU/EXIT itself
    overlay = False   # if True, the screen beneath is drawn first (dim backdrop)

    def __init__(self, app):
        self.app = app

    def on_action(self, action: str):
        """Handle a logical input action."""

    def update(self, dt: float):
        pass

    def draw(self, surf: pygame.Surface, theme):
        pass

    def hints(self) -> list[tuple[str, str]]:
        return [("A", "select"), ("B", "back"), ("LR", "pages")]
