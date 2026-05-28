"""Shared visual primitives so screens stop reinventing the same panel/card
look. Goal: NeoBoX should feel like a polished portable device, not a terminal.

Use:
    panel.card(surf, theme, rect, title="SETTINGS")     # framed content card
    panel.dim_backdrop(surf)                            # behind modal overlays
    panel.key_chip(surf, theme, x, y, "A", "select")   # hint-bar style chip
"""
from __future__ import annotations

import pygame


def card(surf: pygame.Surface, theme, rect: pygame.Rect,
         *, title: str | None = None, alpha: int = 175, border: bool = True):
    """Translucent rounded panel with an accent border. Optional title 'chip'
    bites the top edge so the panel announces what it is at a glance."""
    inner = pygame.Surface(rect.size, pygame.SRCALPHA)
    inner.fill((0, 0, 0, alpha))
    pygame.draw.rect(inner, (0, 0, 0, 0), inner.get_rect(), border_radius=12)
    # round corners by masking — simpler: just blit and draw a border with radius
    surf.blit(inner, rect.topleft)
    if border:
        pygame.draw.rect(surf, theme.color("accent"), rect, width=1, border_radius=12)
    if title:
        font = theme.font("small")
        t = font.render(title.upper(), True, theme.color("accent"))
        cw = t.get_width() + 14
        chip = pygame.Rect(rect.x + 14, rect.y - 8, cw, 16)
        pygame.draw.rect(surf, theme.color("bar"), chip, border_radius=4)
        pygame.draw.rect(surf, theme.color("accent"), chip, width=1, border_radius=4)
        surf.blit(t, (chip.x + 7, chip.y + (chip.height - t.get_height()) // 2 + 1))


def dim_backdrop(surf: pygame.Surface, alpha: int = 140):
    """Darken whatever's underneath — used behind modal overlays so the
    focused content reads clearly."""
    dim = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    dim.fill((0, 0, 0, alpha))
    surf.blit(dim, (0, 0))


def key_chip(surf: pygame.Surface, theme, x: int, y: int, key: str, label: str,
             font=None) -> int:
    """Draw a small `[A] select` style chip used by the hint bar. Returns the
    x-advance (width consumed) so callers can lay multiple chips in a row."""
    f = font or theme.font("small")
    key_surf = f.render(key, True, theme.color("accent"))
    label_surf = f.render(label, True, theme.color("text_dim"))
    kw = key_surf.get_width() + 10
    kh = max(key_surf.get_height(), label_surf.get_height()) + 4
    chip = pygame.Rect(x, y - kh // 2, kw, kh)
    pygame.draw.rect(surf, theme.color("tile"), chip, border_radius=4)
    pygame.draw.rect(surf, theme.color("accent"), chip, width=1, border_radius=4)
    surf.blit(key_surf, (chip.x + 5, chip.centery - key_surf.get_height() // 2))
    surf.blit(label_surf, (chip.right + 6, chip.centery - label_surf.get_height() // 2))
    return kw + 6 + label_surf.get_width() + 14   # spacing to next chip
