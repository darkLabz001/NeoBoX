"""ROM picker: list the ROMs available to a game payload and launch the chosen
one (instead of auto-running the first file found). A payload opts in with
`# neo-roms: <subdir>` (under ~/roms) and `# neo-romext: .cue .pbp .chd`."""
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime

import pygame

from . import Screen
from .. import config, assets
from ..ui import statusbar

ROW_H = 32


class RomPickerScreen(Screen):
    modal = True

    def __init__(self, app, meta: dict):
        super().__init__(app)
        self.meta = meta
        self.title = meta.get("name", "ROMS")
        self.rom_subdir = meta.get("roms") or ""
        self.dir = Path.home() / "roms" / self.rom_subdir
        self.exts = meta.get("romext") or []
        self.roms: list[Path] = []
        self.index = 0
        self.scroll = 0
        self.msg = ""
        
        # UI Layout
        self.list_w = 260
        self.preview_area = pygame.Rect(self.list_w + 10, 40, config.SCREEN_W - self.list_w - 20, config.SCREEN_H - 75)
        
        # Preview Cache
        self._last_preview_path = None
        self._preview_surf = None
        
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

    def _get_preview(self, rom_path: Path):
        # Try to find a preview in assets/previews/<subdir>/<stem>.png or .jpg
        # Also handle (USA), (Disc 1) etc by stripping them
        import re
        stem = rom_path.stem
        clean_stem = re.sub(r"\s*\(.*?\)", "", stem).strip()
        
        paths_to_try = [
            config.ASSETS_DIR / "previews" / self.rom_subdir / f"{stem}.png",
            config.ASSETS_DIR / "previews" / self.rom_subdir / f"{stem}.jpg",
            config.ASSETS_DIR / "previews" / self.rom_subdir / f"{clean_stem}.png",
            config.ASSETS_DIR / "previews" / self.rom_subdir / f"{clean_stem}.jpg",
        ]
        
        for p in paths_to_try:
            if p.exists():
                if p == self._last_preview_path:
                    return self._preview_surf
                try:
                    img = pygame.image.load(str(p)).convert_alpha()
                    # Scale to fit preview area
                    w, h = img.get_size()
                    ratio = min(self.preview_area.width / w, self.preview_area.height / h)
                    img = pygame.transform.smoothscale(img, (int(w * ratio), int(h * ratio)))
                    self._last_preview_path = p
                    self._preview_surf = img
                    return img
                except: pass
        
        self._last_preview_path = None
        self._preview_surf = None
        return None

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, self.title)
        
        font = theme.font("ui")
        small = theme.font("small")
        top = statusbar.HEIGHT + 6
        bottom = config.SCREEN_H - 24

        if not self.roms:
            lines = [f"No ROMs in ~/roms/{self.rom_subdir}",
                     "Upload via the Web UI, then press X to rescan."]
            y = config.SCREEN_H // 2 - 16
            for ln in lines:
                t = small.render(ln, True, theme.color("text_dim"))
                surf.blit(t, t.get_rect(center=(config.SCREEN_W // 2, y)))
                y += 18
            return

        # List Area
        rows = max(1, (bottom - top) // ROW_H)
        if self.index < self.scroll:
            self.scroll = self.index
        elif self.index >= self.scroll + rows:
            self.scroll = self.index - rows + 1
            
        for vi in range(rows):
            i = self.scroll + vi
            if i >= len(self.roms): break
            y = top + vi * ROW_H
            sel = (i == self.index)
            rect = pygame.Rect(8, y, self.list_w, ROW_H - 4)
            if sel:
                pygame.draw.rect(surf, theme.color("tile_sel"), rect, border_radius=6)
                pygame.draw.rect(surf, theme.color("accent"), rect, width=1, border_radius=6)
            
            col = theme.color("accent") if sel else theme.color("text")
            # Clean up display name: strip common tags
            import re
            display_name = re.sub(r"\s*\(USA\)|\s*\(Europe\)|\s*\(Japan\)", "", self.roms[i].stem)
            label = font.render(display_name[:24], True, col)
            surf.blit(label, (rect.x + 10, rect.centery - label.get_height() // 2))

        # Preview Area
        selected_rom = self.roms[self.index]
        preview = self._get_preview(selected_rom)
        
        # Border for preview
        pygame.draw.rect(surf, theme.color("tile"), self.preview_area, border_radius=8)
        pygame.draw.rect(surf, theme.color("accent"), self.preview_area, width=1, border_radius=8)
        
        if preview:
            surf.blit(preview, preview.get_rect(center=self.preview_area.center))
        else:
            # Placeholder text if no image
            txt = small.render("NO PREVIEW", True, theme.color("text_dim"))
            surf.blit(txt, txt.get_rect(center=self.preview_area.center))

        # Metadata under preview
        try:
            mtime = datetime.fromtimestamp(selected_rom.stat().st_mtime).strftime("%Y-%m-%d")
            size = f"{selected_rom.stat().st_size / (1024*1024):.1f} MB"
            info = small.render(f"{size} | {mtime}", True, theme.color("accent"))
            surf.blit(info, (self.preview_area.x + 5, self.preview_area.bottom + 2))
        except: pass

        if len(self.roms) > rows:
            pos = small.render(f"{self.index + 1}/{len(self.roms)}", True, theme.color("accent"))
            surf.blit(pos, (self.list_w - pos.get_width(), bottom + 2))

    def hints(self):
        return [("A", "play"), ("X", "rescan"), ("B", "back")]
