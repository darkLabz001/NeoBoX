"""Shared styled list widget. Caller provides items + a `draw_item` callback
to render each row's content; the widget owns selection, easing scroll, the
scrollbar, the row card background, and the polished selected-row glow — so
every list in the app looks and feels the same.

Usage:
    self.list = ListView(area, row_h=48)
    self.list.set_items(items)

    def on_action(self, action):
        r = self.list.on_action(action)
        if r == "select":
            ...do something with self.list.selected()
        elif r == "back":
            self.app.pop()

    def update(self, dt): self.list.update(dt)
    def is_animating(self): return self.list.is_animating()

    def draw(self, surf, theme):
        def row(surf, theme, rect, item, selected): ...   # caller's row art
        self.list.draw(surf, theme, row)
"""
from __future__ import annotations

from typing import Callable, Any

import pygame


class ListView:
    def __init__(self, area: pygame.Rect, row_h: int = 48, gap: int = 6):
        self.area = area
        self.row_h = row_h
        self.gap = gap
        self.items: list = []
        self.index = 0
        self.scroll = 0.0          # current top-row offset (eased)
        self.target = 0.0          # where scroll is sliding to
        self.visible_rows = max(1, area.height // row_h)
        self._glow_cache: dict[tuple, pygame.Surface] = {}

    # --- items / selection --------------------------------------------------
    def set_items(self, items: list):
        self.items = items
        self.index = min(self.index, max(0, len(items) - 1))
        self._clamp_target()

    def selected(self) -> Any:
        return self.items[self.index] if self.items else None

    def _clamp_target(self):
        max_t = max(0, len(self.items) - self.visible_rows)
        self.target = max(0, min(self.target, max_t))

    def _keep_visible(self):
        if self.index < self.target:
            self.target = self.index
        elif self.index >= self.target + self.visible_rows:
            self.target = self.index - self.visible_rows + 1
        self._clamp_target()

    # --- input --------------------------------------------------------------
    def on_action(self, action: str) -> str | None:
        """Returns 'select' on A, 'back' on B, else None. Updates index."""
        if not self.items:
            return "back" if action == "B" else None
        if action == "UP":
            self.index = (self.index - 1) % len(self.items); self._keep_visible()
        elif action == "DOWN":
            self.index = (self.index + 1) % len(self.items); self._keep_visible()
        elif action == "L":
            self.index = max(0, self.index - self.visible_rows); self._keep_visible()
        elif action == "R":
            self.index = min(len(self.items) - 1, self.index + self.visible_rows); self._keep_visible()
        elif action == "A":
            return "select"
        elif action == "B":
            return "back"
        return None

    # --- animation ----------------------------------------------------------
    def update(self, dt: float):
        d = self.target - self.scroll
        if abs(d) < 0.02:
            self.scroll = self.target
        else:
            self.scroll += d * min(1.0, dt * 14)   # snappy ease

    def is_animating(self) -> bool:
        return abs(self.scroll - self.target) > 0.02

    # --- draw ---------------------------------------------------------------
    def draw(self, surf: pygame.Surface, theme,
             draw_item: Callable[[pygame.Surface, Any, pygame.Rect, Any, bool], None]):
        prev_clip = surf.get_clip()
        surf.set_clip(self.area)

        stride = self.row_h + self.gap
        for i, item in enumerate(self.items):
            iy = self.area.y + int((i - self.scroll) * stride)
            if iy < self.area.y - stride or iy > self.area.bottom:
                continue
            rect = pygame.Rect(self.area.x, iy,
                               self.area.width - (8 if len(self.items) > self.visible_rows else 0),
                               self.row_h)
            sel = (i == self.index)
            self._draw_row_card(surf, theme, rect, sel)
            draw_item(surf, theme, rect, item, sel)

        surf.set_clip(prev_clip)
        self._draw_scrollbar(surf, theme)

    def _draw_row_card(self, surf, theme, rect, selected):
        if selected:
            accent = theme.color("accent")
            # soft outer glow
            key = (rect.width, rect.height, accent.r, accent.g, accent.b)
            glow = self._glow_cache.get(key)
            if glow is None:
                glow = pygame.Surface((rect.width + 16, rect.height + 16), pygame.SRCALPHA)
                for i, a in ((4, 18), (8, 28), (12, 36)):
                    pygame.draw.rect(glow, (accent.r, accent.g, accent.b, a),
                                     (8 - i, 8 - i, rect.width + 2 * i, rect.height + 2 * i),
                                     border_radius=12)
                self._glow_cache[key] = glow
            surf.blit(glow, (rect.x - 8, rect.y - 8))
            pygame.draw.rect(surf, theme.color("tile_sel"), rect, border_radius=10)
            pygame.draw.rect(surf, accent, rect, width=2, border_radius=10)
        else:
            pygame.draw.rect(surf, theme.color("tile"), rect, border_radius=10)

    def _draw_scrollbar(self, surf, theme):
        if len(self.items) <= self.visible_rows:
            return
        track_x = self.area.right - 4
        track_h = self.area.height
        track_y = self.area.y
        thumb_h = max(20, int(track_h * self.visible_rows / len(self.items)))
        max_scroll = max(1, len(self.items) - self.visible_rows)
        thumb_y = track_y + int((track_h - thumb_h) * (self.scroll / max_scroll))
        pygame.draw.rect(surf, theme.color("text_dim"),
                         (track_x, track_y, 2, track_h), border_radius=1)
        pygame.draw.rect(surf, theme.color("accent"),
                         (track_x - 1, thumb_y, 4, thumb_h), border_radius=2)

    # --- standard hints (caller can use directly) --------------------------
    def standard_hints(self) -> list[tuple[str, str]]:
        return [("A", "select"), ("B", "back"), ("LR", "jump")]
