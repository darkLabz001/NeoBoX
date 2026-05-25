"""Volume control overlay — LEFT/RIGHT adjusts the system (HDMI) output level."""
from __future__ import annotations

import pygame

from . import Screen
from .. import audiofx, config

MAX = 1.5   # wpctl allows boost above 1.0; the HAT amp needs it


class VolumeScreen(Screen):
    modal = True
    overlay = True

    def __init__(self, app):
        super().__init__(app)
        self.title = "VOLUME"
        v = audiofx.get_volume()
        self.vol = v if v is not None else 1.0

    def on_action(self, action: str):
        if action == "LEFT":
            self.vol = max(0.0, round(self.vol - 0.1, 2))
            audiofx.set_volume(self.vol)
            self.app.sfx.play("move")
        elif action == "RIGHT":
            self.vol = min(MAX, round(self.vol + 0.1, 2))
            audiofx.set_volume(self.vol)
            self.app.sfx.play("select")
        elif action in ("A", "B", "MENU", "EXIT"):
            self.app.pop()

    def draw(self, surf, theme):
        overlay = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surf.blit(overlay, (0, 0))
        box = pygame.Rect(0, 0, 320, 120)
        box.center = (config.SCREEN_W // 2, config.SCREEN_H // 2)
        pygame.draw.rect(surf, theme.color("bg_alt"), box, border_radius=12)
        pygame.draw.rect(surf, theme.color("accent"), box, width=2, border_radius=12)

        font = theme.font("ui", bold=True)
        t = font.render("VOLUME", True, theme.color("accent"))
        surf.blit(t, (box.x + 16, box.y + 14))

        # bar
        bx, by, bw, bh = box.x + 16, box.y + 56, box.width - 32, 16
        pygame.draw.rect(surf, theme.color("tile"), (bx, by, bw, bh), border_radius=8)
        fill = int(bw * (self.vol / MAX))
        pygame.draw.rect(surf, theme.color("accent"), (bx, by, fill, bh), border_radius=8)
        pct = theme.font("small").render(f"{int(self.vol * 100)}%", True, theme.color("text"))
        surf.blit(pct, (box.right - pct.get_width() - 16, box.y + 16))

    def hints(self):
        return [("←→", "adjust"), ("B", "close")]
