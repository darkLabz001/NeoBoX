"""Simple yes/no confirmation dialog."""
from __future__ import annotations

import pygame

from . import Screen
from .. import config


class ConfirmScreen(Screen):
    modal = True
    overlay = True

    def __init__(self, app, message: str, on_yes):
        super().__init__(app)
        self.message = message
        self.on_yes = on_yes

    def on_action(self, action: str):
        if action == "A":
            self.app.pop()
            self.on_yes()
        elif action in ("B", "MENU", "EXIT"):
            self.app.pop()

    def draw(self, surf, theme):
        # keep prior screen-ish: dim background
        overlay = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surf.blit(overlay, (0, 0))
        box = pygame.Rect(0, 0, 300, 110)
        box.center = (config.SCREEN_W // 2, config.SCREEN_H // 2)
        pygame.draw.rect(surf, theme.color("bg_alt"), box, border_radius=12)
        pygame.draw.rect(surf, theme.color("accent"), box, width=2, border_radius=12)
        font = theme.font("ui")
        msg = font.render(self.message, True, theme.color("text"))
        surf.blit(msg, msg.get_rect(center=(box.centerx, box.y + 36)))
        small = theme.font("small")
        a = small.render("A = yes", True, theme.color("accent"))
        b = small.render("B = no", True, theme.color("danger"))
        surf.blit(a, (box.centerx - 70, box.bottom - 30))
        surf.blit(b, (box.centerx + 20, box.bottom - 30))

    def hints(self):
        return [("A", "yes"), ("B", "no")]
