"""Top status bar: title on the left, wifi/clock/battery on the right."""
from __future__ import annotations

import subprocess
import time

import pygame

HEIGHT = 26


class StatusBar:
    def __init__(self):
        self._wifi = "—"
        self._wifi_checked = 0.0

    def _wifi_state(self) -> str:
        # Refresh at most every 5s; cheap and non-blocking enough for a poll.
        now = time.time()
        if now - self._wifi_checked > 5:
            self._wifi_checked = now
            try:
                out = subprocess.run(
                    ["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"],
                    capture_output=True, text=True, timeout=2,
                ).stdout
                for line in out.splitlines():
                    if line.startswith("yes:"):
                        _, ssid, sig = (line.split(":") + ["", ""])[:3]
                        self._wifi = ssid or "wifi"
                        break
                else:
                    self._wifi = "off"
            except Exception:
                self._wifi = "?"
        return self._wifi

    def draw(self, surf: pygame.Surface, theme, title: str = "NEO", transparent: bool = False):
        w = surf.get_width()
        font = theme.font("small")
        accent = theme.color("accent")
        text = theme.color("text")
        dim = theme.color("text_dim")

        if not transparent:
            pygame.draw.rect(surf, theme.color("bar"), pygame.Rect(0, 0, w, HEIGHT))
            pygame.draw.line(surf, accent, (0, HEIGHT), (w, HEIGHT), 1)
            # Left: title with an accent square
            pygame.draw.rect(surf, accent, (8, HEIGHT // 2 - 4, 8, 8), border_radius=2)
            t = font.render(title.upper(), True, text)
            surf.blit(t, (22, HEIGHT // 2 - t.get_height() // 2))

        # Right: clock then wifi
        clock = time.strftime("%H:%M")
        ct = font.render(clock, True, text)
        surf.blit(ct, (w - ct.get_width() - 8, HEIGHT // 2 - ct.get_height() // 2))

        wifi = self._wifi_state()
        wt = font.render(f"≋ {wifi}", True, dim if wifi in ("off", "?", "—") else accent)
        surf.blit(wt, (w - ct.get_width() - wt.get_width() - 20,
                       HEIGHT // 2 - wt.get_height() // 2))
