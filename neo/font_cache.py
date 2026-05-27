"""Process-wide font and text surface cache to maximize UI performance."""
from __future__ import annotations

import pygame

_FONT_CACHE: dict[tuple[object, int], pygame.font.Font] = {}
_TEXT_CACHE: dict[tuple[pygame.font.Font, str, tuple, bool], pygame.Surface] = {}

def install() -> None:
    """Monkey-patch pygame.font.Font and add a global text renderer."""
    if getattr(pygame.font.Font, "__neo_cached__", False):
        return

    _orig = pygame.font.Font

    def _cached_font(name=None, size=16, *args, **kwargs):
        if not pygame.font.get_init():
            pygame.font.init()

        key = (name, int(size))
        if key in _FONT_CACHE:
            return _FONT_CACHE[key]
        
        try:
            font = _orig(name, int(size))
        except:
            font = _orig(None, int(size))
        
        _FONT_CACHE[key] = font
        return font

    _cached_font.__neo_cached__ = True
    pygame.font.Font = _cached_font

def render_text(font: pygame.font.Font, text: str, color: pygame.Color | tuple, 
                antialias: bool = True) -> pygame.Surface:
    """Render text using an efficient surface cache."""
    # Normalize color to tuple for hashing
    if isinstance(color, pygame.Color):
        color_key = (color.r, color.g, color.b, color.a)
    else:
        color_key = tuple(color)
        
    key = (font, text, color_key, antialias)
    if key in _TEXT_CACHE:
        return _TEXT_CACHE[key]
    
    surf = font.render(text, antialias, color)
    _TEXT_CACHE[key] = surf
    
    # Prune cache if it gets too large
    if len(_TEXT_CACHE) > 500:
        _TEXT_CACHE.clear()
        
    return surf

install()
