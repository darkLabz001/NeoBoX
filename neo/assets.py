"""Icon rendering.

If assets/icons/<name>.png exists it's used; otherwise we procedurally draw a
clean glyph tile so the UI looks finished before real art is added.
"""
from __future__ import annotations

import math

import pygame

from . import config

_cache: dict = {}


_renderable_cache: dict = {}


def _renderable(font: pygame.font.Font, glyph: str) -> bool:
    """True if the font has a real glyph (not the .notdef box) for `glyph`.

    Reliable trick: render the glyph and a Private-Use codepoint that no font
    fills; if the two bitmaps are identical, our glyph is also the .notdef box.
    """
    key = (id(font), glyph)
    if key in _renderable_cache:
        return _renderable_cache[key]
    try:
        white = (255, 255, 255)
        cand = font.render(glyph, True, white)
        miss = font.render("\U000f0000", True, white)
        if cand.get_size() != miss.get_size():
            result = True
        else:
            result = (pygame.image.tostring(cand, "RGB") !=
                      pygame.image.tostring(miss, "RGB"))
    except Exception:
        result = False
    _renderable_cache[key] = result
    return result


def _draw_glyph_icon(size: int, color: pygame.Color, glyph: str, fallback: str,
                     font: pygame.font.Font) -> pygame.Surface:
    """A rounded square badge with an accent glow and a centered glyph."""
    surf = pygame.Surface((size, size), pygame.SRCALPHA).convert_alpha()
    r = max(6, size // 6)
    base = pygame.Color(color.r, color.g, color.b, 40)
    ring = pygame.Color(color.r, color.g, color.b, 230)
    pygame.draw.rect(surf, base, surf.get_rect(), border_radius=r)
    pygame.draw.rect(surf, ring, surf.get_rect().inflate(-2, -2), width=2, border_radius=r)
    text = glyph if _renderable(font, glyph) else (fallback or "•")
    label = font.render(text, True, color)
    surf.blit(label, label.get_rect(center=(size // 2, size // 2)))
    return surf


def icon(name: str, size: int, color: pygame.Color, glyph: str,
         font: pygame.font.Font, fallback: str = "") -> pygame.Surface:
    key = (name, size, color.r, color.g, color.b, glyph, fallback)
    if key in _cache:
        return _cache[key]
    png = config.ICONS_DIR / f"{name}.png"
    if png.exists():
        img = pygame.image.load(str(png)).convert_alpha()
        img = pygame.transform.smoothscale(img, (size, size))
    else:
        img = _draw_glyph_icon(size, color, glyph, fallback, font)
    _cache[key] = img
    return img


_img_cache: dict = {}


def load_icon_image(name: str, size: int):
    """Load assets/icons/<name>.png scaled to size×size (cached). None if absent."""
    key = (name, size)
    if key in _img_cache:
        return _img_cache[key]
    png = config.ICONS_DIR / f"{name}.png"
    img = None
    if png.exists():
        try:
            src = pygame.image.load(str(png)).convert_alpha()
            img = pygame.transform.smoothscale(src, (size, size))
        except Exception:
            img = None
    _img_cache[key] = img
    return img


def load_background(name: str, size: tuple[int, int]):
    """Load assets/backgrounds/<name>.png scaled to size (cached). None if absent."""
    key = ("bg", name, size)
    if key in _img_cache:
        return _img_cache[key]
    png = config.BACKGROUNDS_DIR / f"{name}.png"
    img = None
    if png.exists():
        try:
            src = pygame.image.load(str(png)).convert()
            img = pygame.transform.smoothscale(src, size)
        except Exception:
            img = None
    _img_cache[key] = img
    return img


def vgradient(size: tuple[int, int], top: pygame.Color, bottom: pygame.Color) -> pygame.Surface:
    """Vertical gradient surface, used for the wallpaper."""
    w, h = size
    surf = pygame.Surface(size).convert()
    for y in range(h):
        t = y / max(1, h - 1)
        c = (
            int(top.r + (bottom.r - top.r) * t),
            int(top.g + (bottom.g - top.g) * t),
            int(top.b + (bottom.b - top.b) * t),
        )
        pygame.draw.line(surf, c, (0, y), (w, y))
    return surf
