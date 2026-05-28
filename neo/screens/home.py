"""Home screen — BigBox-style coverflow.

One big card in focus with full-bleed accent wash + ambient breathing behind,
side cards fading off. LR scrolls the wheel; A enters the section. Replaces
the old icon-grid home; the grid implementation is kept in home_grid.py.bak
for reference."""
from __future__ import annotations

import json
import math

import pygame

from . import Screen
from .section import SectionScreen
from .. import assets, config

# Card sizes (focused / one-off / two-off)
CARD_W = 220
CARD_H = 230
SIDE_W = 130
SIDE_H = 170
FAR_W = 90
FAR_H = 130
CARD_SPACING = 175    # px between adjacent card centers


class HomeScreen(Screen):
    title = "NEOBOX"

    def __init__(self, app):
        super().__init__(app)
        with open(config.SECTIONS_FILE) as fh:
            self.sections = json.load(fh)["sections"]
        self.n = len(self.sections)
        self.index = 0
        self.scroll = 0.0
        self.target = 0.0
        self._t = 0.0          # for ambient breathing
        # pre-load icon art at the sizes we use, so scrolling never stutters
        self._icons: dict[tuple[str, int], pygame.Surface] = {}
        for s in self.sections:
            for sz in (int(CARD_W * 0.7), int(SIDE_W * 0.7), int(FAR_W * 0.7)):
                key = (s.get("icon", s["id"]), sz)
                img = assets.load_icon_image(key[0], sz)
                if img is not None:
                    self._icons[key] = img.convert_alpha()

    # --- input ----------------------------------------------------------
    def on_action(self, action: str):
        if action in ("LEFT", "L"):
            self.index = (self.index - 1) % self.n
            self.target = float(self.index)
        elif action in ("RIGHT", "R"):
            self.index = (self.index + 1) % self.n
            self.target = float(self.index)
        elif action == "DOWN":     # tiny shortcut: jump to Settings
            self.index = self.n - 1
            self.target = float(self.index)
        elif action == "A":
            self.app.push(SectionScreen(self.app, self.sections[self.index]))

    # --- animation ------------------------------------------------------
    def update(self, dt: float):
        self._t += dt
        # eased scroll, wrap-aware (always take the shortest path on the circle)
        d = self.target - self.scroll
        if d > self.n / 2:
            self.scroll += self.n
            d = self.target - self.scroll
        elif d < -self.n / 2:
            self.scroll -= self.n
            d = self.target - self.scroll
        if abs(d) < 0.003:
            self.scroll = self.target
        else:
            self.scroll += d * min(1.0, dt * 16)

    def is_animating(self):
        return True   # ambient drift + breathing run constantly

    # --- draw -----------------------------------------------------------
    def draw(self, surf, theme):
        self._draw_background(surf, theme)
        self._draw_wheel(surf, theme)
        self._draw_label(surf, theme)
        # transparent statusbar (clock/wifi only)
        self.app.statusbar.draw(surf, theme, "NEOBOX", transparent=True)

    def _draw_background(self, surf, theme):
        # base
        surf.fill(theme.color("bg"))
        # big breathing accent glow behind the focused card
        cx = config.SCREEN_W // 2
        cy = config.SCREEN_H // 2 - 14
        accent = theme.color("accent")
        breath = 0.85 + 0.15 * math.sin(self._t * 0.55)
        for radius, alpha in ((230, 22), (170, 32), (110, 42), (60, 60)):
            r = int(radius * breath)
            a = int(alpha * breath)
            g = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(g, (accent.r, accent.g, accent.b, a), (r, r), r)
            surf.blit(g, (cx - r, cy - r))

    def _draw_wheel(self, surf, theme):
        cx = config.SCREEN_W // 2
        cy = config.SCREEN_H // 2 - 12
        # collect visible cards with their wrap-aware horizontal offset
        items = []
        for i in range(self.n):
            d = i - self.scroll
            if d > self.n / 2:  d -= self.n
            if d < -self.n / 2: d += self.n
            if abs(d) > 2.6: continue
            items.append((abs(d), d, i))
        # furthest first so the focused card renders on top
        items.sort(reverse=True)
        for _, d, i in items:
            x = cx + int(d * CARD_SPACING * (1 - abs(d) * 0.05))
            self._draw_card(surf, theme, self.sections[i], x, cy, d)

    def _draw_card(self, surf, theme, section, cx, cy, off):
        absd = abs(off)
        # interp size between focused / side / far
        if absd <= 1.0:
            t = absd
            w = int(CARD_W + (SIDE_W - CARD_W) * t)
            h = int(CARD_H + (SIDE_H - CARD_H) * t)
            alpha = int(255 + (170 - 255) * t)
        else:
            t = min(1.0, (absd - 1.0))
            w = int(SIDE_W + (FAR_W - SIDE_W) * t)
            h = int(SIDE_H + (FAR_H - SIDE_H) * t)
            alpha = int(170 + (60 - 170) * t)
        focus = absd < 0.45
        rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
        accent = theme.color("accent")

        # card panel
        card = pygame.Surface((w, h), pygame.SRCALPHA)
        card.fill((18, 14, 30, int(alpha * 0.92)))
        pygame.draw.rect(card, (accent.r, accent.g, accent.b, alpha),
                         card.get_rect(), width=2 if focus else 1, border_radius=14)
        surf.blit(card, rect.topleft)

        # icon — pick the cached size closest to what we need
        target_isize = int(w * 0.7)
        icon_name = section.get("icon", section["id"])
        # find the closest cached size
        candidates = [k for k in self._icons if k[0] == icon_name]
        if candidates:
            key = min(candidates, key=lambda k: abs(k[1] - target_isize))
            icon = self._icons[key]
            if icon.get_width() != target_isize:
                icon = pygame.transform.smoothscale(icon, (target_isize, target_isize))
            if alpha < 255:
                icon = icon.copy()
                icon.set_alpha(alpha)
            irect = icon.get_rect(center=(rect.centerx, rect.centery - h // 12))
            surf.blit(icon, irect)

        # title under the icon (focused card only — keeps side cards clean)
        if focus:
            font = theme.font("ui", bold=True)
            t = font.render(section["name"].upper(), True, theme.color("accent"))
            surf.blit(t, t.get_rect(midbottom=(rect.centerx, rect.bottom - 14)))

    def _draw_label(self, surf, theme):
        # Big focused-section title above the card
        sec = self.sections[self.index]
        big = theme.font("title", bold=True)
        small = theme.font("small")
        accent = theme.color("accent")
        dim = theme.color("text_dim")
        # tagline under the wheel
        tag_y = config.SCREEN_H - 52
        tag = small.render("CONTROL  ·  ANALYZE  ·  DOMINATE", True, dim)
        surf.blit(tag, tag.get_rect(center=(config.SCREEN_W // 2, tag_y)))

    def hints(self):
        return [("LR", "wheel"), ("A", "open"), ("DOWN", "settings")]
