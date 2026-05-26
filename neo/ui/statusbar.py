"""Top status bar: title on the left, wifi/clock/battery on the right."""
from __future__ import annotations

import subprocess
import time

import pygame

HEIGHT = 26


class StatusBar:
    def __init__(self):
        self._wifi = "—"
        self._ip = ""
        self._checked = 0.0

    def _refresh_net(self):
        """Refresh SSID + IP at most every 5s; cheap and non-blocking enough."""
        now = time.time()
        if now - self._checked <= 5:
            return
        self._checked = now
        try:
            out = subprocess.run(
                ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
                capture_output=True, text=True, timeout=2,
            ).stdout
            self._wifi = next((l.split(":", 1)[1] or "wifi"
                               for l in out.splitlines() if l.startswith("yes:")), "off")
        except Exception:
            self._wifi = "?"
        # Local IP on whatever network we're routed through (no packets sent).
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self._ip = s.getsockname()[0]
            s.close()
        except Exception:
            self._ip = ""

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

        # Right side, right-to-left: clock, IP, wifi SSID (12-hour, e.g. "9:35 PM")
        self._refresh_net()
        cy = HEIGHT // 2
        x = w - 8
        clock = font.render(time.strftime("%I:%M %p").lstrip("0"), True, text)
        x -= clock.get_width()
        surf.blit(clock, (x, cy - clock.get_height() // 2))

        if self._ip:
            ipt = font.render(self._ip, True, dim)
            x -= ipt.get_width() + 10
            surf.blit(ipt, (x, cy - ipt.get_height() // 2))

        offline = self._wifi in ("off", "?", "—")
        wt = font.render(f"≋ {self._wifi}", True, dim if offline else accent)
        x -= wt.get_width() + 10
        surf.blit(wt, (x, cy - wt.get_height() // 2))
