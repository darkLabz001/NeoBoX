"""Top status bar: title on the left, wifi/clock/battery on the right."""
from __future__ import annotations

import subprocess
import time

import pygame
from ..font_cache import render_text

HEIGHT = 26


class StatusBar:
    def __init__(self):
        self._ip = ""
        self._wifi = "—"
        self._last_poll = 0.0

    def _poll(self):
        now = time.time()
        if now - self._last_poll < 5.0:
            return
        self._last_poll = now
        try:
            # Quick SSID check
            out = subprocess.check_output(
                ["iwgetid", "-r"], stderr=subprocess.DEVNULL).decode().strip()
            self._wifi = out or "off"
        except Exception:
            self._wifi = "off"

        try:
            # IP on wlan0
            out = subprocess.check_output(
                ["hostname", "-I"], stderr=subprocess.DEVNULL).decode().split()
            self._ip = out[0] if out else ""
        except Exception:
            self._ip = ""

    def draw(self, surf: pygame.Surface, theme, title: str, transparent=False):
        self._poll()
        if not transparent:
            pygame.draw.rect(surf, theme.color("bar"), (0, 0, surf.get_width(), HEIGHT))
            pygame.draw.line(surf, theme.color("text_dim"), (0, HEIGHT - 1), (surf.get_width(), HEIGHT - 1))

        font = theme.font("small")
        title_font = theme.font("ui")
        accent = theme.color("accent")
        text = theme.color("text")
        dim = theme.color("text_dim")

        # Title
        tt = render_text(title_font, title.upper(), text)
        surf.blit(tt, (10, HEIGHT // 2 - tt.get_height() // 2))

        # Right side: clock, IP, wifi
        x = surf.get_width() - 10
        cy = HEIGHT // 2

        clock_str = time.strftime("%I:%M %p").lstrip("0")
        clock = render_text(font, clock_str, accent)
        x -= clock.get_width()
        surf.blit(clock, (x, cy - clock.get_height() // 2))

        if self._ip:
            ipt = render_text(font, self._ip, accent)
            x -= ipt.get_width() + 10
            surf.blit(ipt, (x, cy - ipt.get_height() // 2))

        offline = self._wifi in ("off", "?", "—")
        wt = render_text(font, f"≋ {self._wifi}", dim if offline else accent)
        x -= wt.get_width() + 10
        surf.blit(wt, (x, cy - wt.get_height() // 2))
