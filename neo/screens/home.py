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
from .. import assets, config

# Card sizes (focused / one-off / two-off)
CARD_W = 220
CARD_H = 230
SIDE_W = 130
SIDE_H = 170
FAR_W = 90
FAR_H = 130
CARD_SPACING = 175    # px between adjacent card centers

# Each section has its own accent color — the wash behind the focused card
# lerps between them as you scroll, so the whole screen breathes the section's
# color. This is the single most BigBox-alive thing on the home.
SECTION_COLORS: dict[str, tuple[int, int, int]] = {
    "recon":     (255, 92, 171),   # pink/magenta
    "wifi":      (92, 232, 255),   # cyan
    "bluetooth": (92, 138, 255),   # blue
    "network":   (92, 255, 192),   # green-cyan
    "web":       (255, 157, 92),   # orange
    "passwords": (255, 215, 92),   # gold
    "social":    (177, 92, 255),   # purple
    "games":     (255, 92, 110),   # red-orange
    "system":    (160, 168, 200),  # cool silver
    "media":     (255, 124, 92),   # warm coral
    "settings":  (255, 92, 171),   # default pink (matches theme accent)
}


def _section_color(sec: dict) -> tuple[int, int, int]:
    return SECTION_COLORS.get(sec.get("id", ""), (255, 92, 171))


def _lerp_color(a: tuple, b: tuple, t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


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
            self.app.open_section(self.sections[self.index])

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
            self.scroll += d * min(1.0, dt * 22)   # snappier glide

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
        # The wash blends between the section colors of the two cards we're
        # between, so the whole screen color-shifts as you wheel.
        i_lo = int(self.scroll) % self.n
        i_hi = (i_lo + 1) % self.n
        t = self.scroll - int(self.scroll)
        c = _lerp_color(_section_color(self.sections[i_lo]),
                        _section_color(self.sections[i_hi]), t)
        cx = config.SCREEN_W // 2
        cy = config.SCREEN_H // 2 - 14
        breath = 0.85 + 0.15 * math.sin(self._t * 0.55)
        for radius, alpha in ((230, 22), (170, 32), (110, 44), (60, 64)):
            r = int(radius * breath)
            a = int(alpha * breath)
            g = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(g, (c[0], c[1], c[2], a), (r, r), r)
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
        # each card's own color (border + focused title) — the focused one's
        # color also drives the background wash, tying it all together.
        c = _section_color(section)

        # card panel
        card = pygame.Surface((w, h), pygame.SRCALPHA)
        card.fill((18, 14, 30, int(alpha * 0.92)))
        pygame.draw.rect(card, (c[0], c[1], c[2], alpha),
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
            t = font.render(section["name"].upper(), True, c)
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
