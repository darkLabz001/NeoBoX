"""Scrollable, paginated grid of icon tiles with a selection cursor."""
from __future__ import annotations

import pygame

from .. import assets, config


class IconGrid:
    def __init__(self, items: list[dict], area: pygame.Rect, cols: int = 3, rows: int = 2,
                 margin: int = 16, gap: int = 12):
        self.items = items
        self.area = area
        self.cols = cols
        self.rows = rows
        self.margin = margin
        self.gap = gap
        self.per_page = cols * rows
        self.index = 0
        self.scroll_x = 0.0          # current pixel offset
        self.target_x = 0.0          # where we're sliding to
        self._compute_tile_size()

    def _compute_tile_size(self):
        a = self.area
        self.page_w = a.width
        self.tile_w = (a.width - 2 * self.margin - (self.cols - 1) * self.gap) // self.cols
        self.tile_h = (a.height - 2 * self.margin - (self.rows - 1) * self.gap) // self.rows

    @property
    def page_count(self) -> int:
        return max(1, (len(self.items) + self.per_page - 1) // self.per_page)

    @property
    def page(self) -> int:
        return self.index // self.per_page

    def selected(self) -> dict | None:
        return self.items[self.index] if self.items else None

    # --- navigation -----------------------------------------------------
    def _set_index(self, i: int):
        self.index = max(0, min(len(self.items) - 1, i))
        self.target_x = self.page * self.page_w

    def move(self, dx: int, dy: int):
        if not self.items:
            return
        pos = self.index % self.per_page
        row, col = divmod(pos, self.cols)
        if dy:
            row = (row + dy) % self.rows
            new = self.page * self.per_page + row * self.cols + col
            if new < len(self.items):
                self._set_index(new)
            return
        if dx:
            col += dx
            if col < 0:                       # off left edge -> prev page, last col
                if self.page > 0:
                    self._set_index((self.page - 1) * self.per_page + row * self.cols + (self.cols - 1))
            elif col >= self.cols:            # off right edge -> next page, first col
                if self.page < self.page_count - 1:
                    self._set_index((self.page + 1) * self.per_page + row * self.cols)
            else:
                self._set_index(self.page * self.per_page + row * self.cols + col)

    def page_jump(self, d: int):
        new_page = max(0, min(self.page_count - 1, self.page + d))
        self._set_index(new_page * self.per_page)

    # --- update / draw --------------------------------------------------
    def update(self, dt: float):
        # Ease scroll toward target.
        diff = self.target_x - self.scroll_x
        if abs(diff) < 0.5:
            self.scroll_x = self.target_x
        else:
            self.scroll_x += diff * min(1.0, dt * 12)

    def _tile_rect(self, page: int, pos: int) -> pygame.Rect:
        row, col = divmod(pos, self.cols)
        x = self.area.x + page * self.page_w + self.margin + col * (self.tile_w + self.gap)
        y = self.area.y + self.margin + row * (self.tile_h + self.gap)
        return pygame.Rect(int(x - self.scroll_x), int(y), self.tile_w, self.tile_h)

    def draw(self, surf: pygame.Surface, theme):
        prev_clip = surf.get_clip()
        surf.set_clip(self.area)
        icon_font = theme.font("title", bold=True)
        label_font = theme.font("tile")

        # Only draw pages that can be visible given the current scroll.
        first = max(0, int(self.scroll_x // self.page_w) - 1)
        for page in range(first, min(self.page_count, first + 3)):
            for pos in range(self.per_page):
                idx = page * self.per_page + pos
                if idx >= len(self.items):
                    break
                item = self.items[idx]
                rect = self._tile_rect(page, pos)
                if rect.right < self.area.left or rect.left > self.area.right:
                    continue
                self._draw_tile(surf, theme, rect, item, selected=(idx == self.index),
                                icon_font=icon_font, label_font=label_font)
        surf.set_clip(prev_clip)
        self._draw_page_dots(surf, theme)

    def _draw_tile(self, surf, theme, rect, item, selected, icon_font, label_font):
        accent = pygame.Color(item["color"]) if item.get("color") else theme.color("accent")
        image_name = item.get("image")
        has_image = bool(image_name) and (config.ICONS_DIR / f"{image_name}.png").exists()
        show_label = not item.get("hide_label")

        if has_image:
            avail_h = rect.height - (16 if show_label else 4)
            isize = max(24, min(rect.width - 4, avail_h))
            img = assets.load_icon_image(image_name, isize)
            cy = rect.y + isize // 2 + (2 if show_label else (rect.height - isize) // 2)
            irect = img.get_rect(center=(rect.centerx, cy))
            if selected:
                b = irect.inflate(10, 10)
                pygame.draw.rect(surf, accent, b, width=2, border_radius=12)
                pygame.draw.rect(surf, pygame.Color(accent.r, accent.g, accent.b, 80),
                                 b.inflate(6, 6), width=2, border_radius=14)
            surf.blit(img, irect)
            if show_label:
                self._label(surf, theme, label_font, item["name"], rect)
            return

        # glyph-badge tile (payloads / no image)
        bg = theme.color("tile_sel") if selected else theme.color("tile")
        pygame.draw.rect(surf, bg, rect, border_radius=10)
        if selected:
            pygame.draw.rect(surf, accent, rect, width=2, border_radius=10)
        isize = max(28, min(rect.width, rect.height) - 46)
        ic = assets.icon(item.get("icon", item["name"]), isize, accent,
                         item.get("glyph", item["name"][:1].upper()), icon_font,
                         fallback=item["name"][:1].upper())
        surf.blit(ic, ic.get_rect(center=(rect.centerx, rect.y + isize // 2 + 12)))
        self._label(surf, theme, label_font, item["name"], rect)

    def _label(self, surf, theme, font, text, rect):
        if font.size(text)[0] > rect.width - 6:
            while text and font.size(text + "…")[0] > rect.width - 6:
                text = text[:-1]
            text += "…"
        center = (rect.centerx, rect.bottom - 10)
        shadow = font.render(text, True, (0, 0, 0))
        label = font.render(text, True, theme.color("text"))
        srect = shadow.get_rect(center=(center[0] + 1, center[1] + 1))
        surf.blit(shadow, srect)
        surf.blit(label, label.get_rect(center=center))

    def _draw_page_dots(self, surf, theme):
        if self.page_count <= 1:
            return
        n = self.page_count
        spacing = 16
        cx = self.area.centerx - ((n - 1) * spacing) // 2
        y = self.area.bottom - 6
        for i in range(n):
            p = (cx + i * spacing, y)
            if i == self.page:
                pygame.draw.circle(surf, theme.color("accent"), p, 4)
            else:
                pygame.draw.circle(surf, theme.color("text_dim"), p, 3, width=1)  # hollow
