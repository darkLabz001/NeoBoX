"""ROM picker: list the ROMs available to a game payload and launch the chosen
one (instead of auto-running the first file found). A payload opts in with
`# neo-roms: <subdir>` (under ~/roms) and `# neo-romext: .cue .pbp .chd`."""
from __future__ import annotations

from pathlib import Path

import pygame

from . import Screen
from .. import config
from ..ui import statusbar

ROW_H = 26


class RomPickerScreen(Screen):
    modal = True   # own MENU/EXIT so they don't pop us mid-list

    def __init__(self, app, meta: dict):
        super().__init__(app)
        self.meta = meta
        self.title = meta.get("name", "ROMS")
        self.dir = Path.home() / "roms" / (meta.get("roms") or "")
        self.exts = meta.get("romext") or []
        self.roms: list[Path] = []
        self.index = 0
        self.scroll = 0
        self.msg = ""
        self._rescan()

    def _rescan(self):
        roms = []
        if self.dir.is_dir():
            for f in sorted(self.dir.iterdir()):
                if f.is_file() and (not self.exts or f.suffix.lower() in self.exts):
                    roms.append(f)
        self.roms = roms
        self.index = min(self.index, max(0, len(roms) - 1))

    def on_action(self, action: str):
        if action in ("B", "MENU", "EXIT"):
            self.app.pop()
        elif action == "X":
            self._rescan()
            self.msg = f"{len(self.roms)} ROM(s)"
        elif not self.roms:
            return
        elif action == "UP":
            self.index = (self.index - 1) % len(self.roms)
        elif action == "DOWN":
            self.index = (self.index + 1) % len(self.roms)
        elif action == "A":
            self.app.launch_payload(self.meta, {}, rom=str(self.roms[self.index]))

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, self.title)
        font = theme.font("ui")
        small = theme.font("small")
        top = statusbar.HEIGHT + 6
        bottom = config.SCREEN_H - 24

        if not self.roms:
            lines = [f"No ROMs in ~/roms/{self.meta.get('roms', '')}",
                     "Upload via the Web UI, then press X to rescan."]
            y = config.SCREEN_H // 2 - 16
            for ln in lines:
                t = small.render(ln, True, theme.color("text_dim"))
                surf.blit(t, t.get_rect(center=(config.SCREEN_W // 2, y)))
                y += 18
            return

        rows = max(1, (bottom - top) // ROW_H)
        if self.index < self.scroll:
            self.scroll = self.index
        elif self.index >= self.scroll + rows:
            self.scroll = self.index - rows + 1
        for vi in range(rows):
            i = self.scroll + vi
            if i >= len(self.roms):
                break
            y = top + vi * ROW_H
            sel = (i == self.index)
            rect = pygame.Rect(8, y, config.SCREEN_W - 16, ROW_H - 4)
            if sel:
                pygame.draw.rect(surf, theme.color("tile_sel"), rect, border_radius=6)
                pygame.draw.rect(surf, theme.color("accent"), rect, width=1, border_radius=6)
            col = theme.color("accent") if sel else theme.color("text")
            label = font.render(self.roms[i].stem[:32], True, col)
            surf.blit(label, (rect.x + 10, rect.centery - label.get_height() // 2))

        if len(self.roms) > rows:   # simple position indicator
            pos = small.render(f"{self.index + 1}/{len(self.roms)}", True, theme.color("text_dim"))
            surf.blit(pos, (config.SCREEN_W - pos.get_width() - 10, bottom + 2))
        if self.msg:
            surf.blit(small.render(self.msg, True, theme.color("text_dim")), (10, bottom + 2))

    def hints(self):
        return [("A", "play"), ("X", "rescan"), ("B", "back")]
