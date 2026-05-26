#!/usr/bin/env python3
"""Slice the 4x2 Pwnagotchi mood sheet into white-on-transparent sprites.
Run: python3 tools/slice_pwn_sprites.py"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets/sprites/pwn/_sheet.png"
OUT = ROOT / "assets/sprites/pwn"
MOODS = [["intense", "excited", "calm", "alert"],
         ["sad", "happy", "look", "sleep"]]

im = Image.open(SRC).convert("L")
W, H = im.size
cols, rows = 4, 2
cw, ch = W // cols, H // rows
for r in range(rows):
    for c in range(cols):
        cell = im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
        alpha = cell.point(lambda v: 255 - v)            # dark ink -> opaque
        white = Image.new("L", cell.size, 255)
        rgba = Image.merge("RGBA", (white, white, white, alpha))
        mask = alpha.point(lambda v: 255 if v > 40 else 0)
        bbox = mask.getbbox()
        if bbox:
            pad = 10
            bbox = (max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                    min(cell.size[0], bbox[2] + pad), min(cell.size[1], bbox[3] + pad))
            rgba = rgba.crop(bbox)
        name = MOODS[r][c]
        rgba.save(OUT / f"{name}.png")
        print(f"{name}: {rgba.size}")
