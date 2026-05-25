"""Theme loading: colors and fonts from themes/<name>.json.

A theme is intentionally simple so users can drop in new .json files.
Missing keys fall back to the built-in default, so partial themes work.
"""
from __future__ import annotations

import json

import pygame

from . import config

_DEFAULT = {
    "name": "midnight",
    "colors": {
        "bg": "#0a0e14",
        "bg_alt": "#0f1622",
        "bar": "#070a10",
        "accent": "#27e07d",
        "accent2": "#21c7e0",
        "text": "#e6edf3",
        "text_dim": "#6b7889",
        "tile": "#121a26",
        "tile_sel": "#1b2738",
        "tile_border": "#27e07d",
        "danger": "#ff5470",
        "warn": "#ffb454",
    },
    "fonts": {
        "family": "dejavusansmono",
        "family_bold": "dejavusansmono",
        "ui": 16,
        "small": 12,
        "tile": 14,
        "title": 22,
    },
    "wallpaper": None,
}


def _hex(value: str) -> pygame.Color:
    return pygame.Color(value)


class Theme:
    def __init__(self, data: dict):
        merged = {**_DEFAULT, **data}
        merged["colors"] = {**_DEFAULT["colors"], **data.get("colors", {})}
        merged["fonts"] = {**_DEFAULT["fonts"], **data.get("fonts", {})}
        self.name = merged["name"]
        self.raw = merged
        self.colors = {k: _hex(v) for k, v in merged["colors"].items()}
        self._fonts: dict = {}
        self._fdef = merged["fonts"]
        self.wallpaper = merged.get("wallpaper")

    def color(self, key: str) -> pygame.Color:
        return self.colors.get(key, self.colors["text"])

    def font(self, size_key: str = "ui", bold: bool = False) -> pygame.font.Font:
        cache_key = (size_key, bold)
        if cache_key in self._fonts:
            return self._fonts[cache_key]
        size = int(self._fdef.get(size_key, 16))
        family = self._fdef.get("family_bold" if bold else "family", "dejavusansmono")
        path = pygame.font.match_font(family, bold=bold) or pygame.font.match_font("dejavusansmono") \
            or pygame.font.get_default_font()
        font = pygame.font.Font(path, size)
        self._fonts[cache_key] = font
        return font


def load(name: str = config.DEFAULT_THEME) -> Theme:
    path = config.THEMES_DIR / f"{name}.json"
    if path.exists():
        with open(path) as fh:
            return Theme(json.load(fh))
    return Theme({"name": name})
