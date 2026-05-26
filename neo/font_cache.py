"""Process-wide font cache for pygame to reduce CPU usage on the Pi."""
from __future__ import annotations

import pygame


def install() -> None:
    if getattr(pygame.font.Font, "__neo_cached__", False):
        return

    _orig = pygame.font.Font
    _cache: dict[tuple[object, int], pygame.font.Font] = {}

    def _cached_font(name=None, size=16, *args, **kwargs):
        if not pygame.font.get_init():
            pygame.font.init()

        if not args and not kwargs:
            key = (name, int(size))
            cached = _cache.get(key)
            if cached is not None:
                return cached
            try:
                font = _orig(name, int(size))
            except Exception:
                return _orig(name, int(size))
            _cache[key] = font
            return font
        return _orig(name, size, *args, **kwargs)

    _cached_font.__neo_cached__ = True
    pygame.font.Font = _cached_font

install()
