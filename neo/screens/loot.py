"""Loot Browser screen — Unified visualizer for handshakes, credentials, and scans."""
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime

import pygame

from . import Screen
from .. import config

PHASE_CATEGORIES = "categories"
PHASE_FILES = "files"
PHASE_VIEW = "view"

class LootScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.phase = PHASE_CATEGORIES
        self.loot_dir = Path("loot")
        self.categories = [
            {"id": "handshakes", "label": "HANDSHAKES", "path": self.loot_dir / "handshakes", "icon": "wifi"},
            {"id": "passwords", "label": "PASSWORDS", "path": self.loot_dir / "passwords", "icon": "passwords"},
            {"id": "scans", "label": "SCANS", "path": self.loot_dir / "scans", "icon": "recon"},
            {"id": "captures", "label": "CAPTURES", "path": self.loot_dir / "captures", "icon": "media"},
        ]
        self.category_index = 0
        
        self.files = []
        self.file_index = 0
        
        self.view_title = ""
        self.view_content = []
        self.view_scroll = 0
        self.view_line_h = 0
        
        self._ensure_dirs()

    def _ensure_dirs(self):
        for cat in self.categories:
            cat["path"].mkdir(parents=True, exist_ok=True)

    def _load_files(self):
        cat = self.categories[self.category_index]
        path = cat["path"]
        self.files = sorted(
            [f for f in path.iterdir() if f.is_file() and not f.name.startswith(".")],
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        self.file_index = 0

    def _load_file_content(self, path: Path):
        self.view_title = path.name
        self.view_scroll = 0
        try:
            if path.suffix in (".pcap", ".pcapng"):
                size = path.stat().st_size
                mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                self.view_content = [
                    f"BINARY CAPTURE: {path.name}",
                    f"SIZE: {size} bytes",
                    f"MODIFIED: {mtime}",
                    "",
                    "Export this file to a PC for analysis in",
                    "Wireshark or other tools."
                ]
            else:
                with open(path, "r", errors="replace") as f:
                    self.view_content = f.read().splitlines()
        except Exception as e:
            self.view_content = [f"Error reading file: {e}"]

    def on_action(self, action: str):
        if self.phase == PHASE_CATEGORIES:
            if action == "UP":
                self.category_index = (self.category_index - 1) % len(self.categories)
            elif action == "DOWN":
                self.category_index = (self.category_index + 1) % len(self.categories)
            elif action == "A":
                self._load_files()
                self.phase = PHASE_FILES
            elif action == "B":
                self.app.pop()

        elif self.phase == PHASE_FILES:
            if action == "UP":
                if self.files:
                    self.file_index = (self.file_index - 1) % len(self.files)
            elif action == "DOWN":
                if self.files:
                    self.file_index = (self.file_index + 1) % len(self.files)
            elif action == "A":
                if self.files:
                    self._load_file_content(self.files[self.file_index])
                    self.phase = PHASE_VIEW
            elif action == "B":
                self.phase = PHASE_CATEGORIES

        elif self.phase == PHASE_VIEW:
            if action == "UP":
                self.view_scroll = max(0, self.view_scroll - 5)
            elif action == "DOWN":
                max_scroll = max(0, len(self.view_content) - 10) # rough estimate
                self.view_scroll = min(max_scroll, self.view_scroll + 5)
            elif action == "B":
                self.phase = PHASE_FILES

    def update(self, dt: float):
        pass

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        
        title_map = {
            PHASE_CATEGORIES: "LOOT CATEGORIES",
            PHASE_FILES: f"LOOT: {self.categories[self.category_index]['label']}",
            PHASE_VIEW: f"VIEW: {self.view_title}"
        }
        self.app.statusbar.draw(surf, theme, title_map[self.phase])

        area = pygame.Rect(10, 40, config.SCREEN_W - 20, config.SCREEN_H - 75)
        
        if self.phase == PHASE_CATEGORIES:
            self._draw_categories(surf, area, theme)
        elif self.phase == PHASE_FILES:
            self._draw_files(surf, area, theme)
        elif self.phase == PHASE_VIEW:
            self._draw_view(surf, area, theme)

    def _draw_categories(self, surf, area, theme):
        row_h = 50
        for i, cat in enumerate(self.categories):
            sel = i == self.category_index
            rect = pygame.Rect(area.x, area.y + i * (row_h + 5), area.width, row_h)
            
            bg = theme.color("tile_sel") if sel else theme.color("tile")
            border = theme.color("accent") if sel else theme.color("text_dim")
            
            pygame.draw.rect(surf, bg, rect, border_radius=8)
            pygame.draw.rect(surf, border, rect, width=1, border_radius=8)
            
            # Icon (procedural or loaded)
            from .. import assets
            font_ui = theme.font("ui")
            # Try to load real icon if exists, else use name
            ic = assets.load_icon_image(cat["icon"], 32)
            if ic:
                surf.blit(ic, (rect.x + 10, rect.y + row_h // 2 - 16))
            
            surf.blit(font_ui.render(cat["label"], True, theme.color("text")), (rect.x + 50, rect.y + 15))
            
            # Count files
            count = len(list(cat["path"].glob("*")))
            small = theme.font("small")
            surf.blit(small.render(f"{count} files", True, theme.color("text_dim")), (rect.right - 60, rect.y + 18))

    def _draw_files(self, surf, area, theme):
        if not self.files:
            font = theme.font("ui")
            txt = font.render("No files found.", True, theme.color("text_dim"))
            surf.blit(txt, (area.centerx - txt.get_width() // 2, area.centery))
            return

        row_h = 24
        visible_rows = area.height // row_h
        start_idx = max(0, self.file_index - visible_rows // 2)
        end_idx = min(len(self.files), start_idx + visible_rows)
        if end_idx - start_idx < visible_rows:
            start_idx = max(0, end_idx - visible_rows)

        font = theme.font("ui")
        small = theme.font("small")
        
        for i in range(start_idx, end_idx):
            sel = i == self.file_index
            f = self.files[i]
            y = area.y + (i - start_idx) * row_h
            
            if sel:
                pygame.draw.rect(surf, theme.color("tile_sel"), (area.x, y, area.width, row_h), border_radius=4)
                pygame.draw.rect(surf, theme.color("accent"), (area.x, y, area.width, row_h), width=1, border_radius=4)
            
            name_txt = font.render(f.name[:35], True, theme.color("text"))
            surf.blit(name_txt, (area.x + 5, y + 2))
            
            size = f"{f.stat().st_size / 1024:.1f}K"
            size_txt = small.render(size, True, theme.color("text_dim"))
            surf.blit(size_txt, (area.right - 50, y + 5))

    def _draw_view(self, surf, area, theme):
        font = theme.font("small")
        self.view_line_h = font.get_height() + 2
        visible_lines = area.height // self.view_line_h
        
        prev_clip = surf.get_clip()
        surf.set_clip(area)
        
        y = area.y
        for i in range(self.view_scroll, min(len(self.view_content), self.view_scroll + visible_lines)):
            line = self.view_content[i]
            surf.blit(font.render(line[:80], True, theme.color("text")), (area.x, y))
            y += self.view_line_h
            
        surf.set_clip(prev_clip)
        
        # Scrollbar
        if len(self.view_content) > visible_lines:
            frac = visible_lines / len(self.view_content)
            bar_h = max(10, int(area.height * frac))
            pos = self.view_scroll / (len(self.view_content) - visible_lines)
            by = area.y + int((area.height - bar_h) * pos)
            pygame.draw.rect(surf, theme.color("text_dim"), (area.right - 3, by, 3, bar_h), border_radius=2)

    def hints(self):
        if self.phase == PHASE_CATEGORIES:
            return [("B", "back"), ("A", "open"), ("↑↓", "nav")]
        elif self.phase == PHASE_FILES:
            return [("B", "back"), ("A", "view"), ("↑↓", "nav")]
        else:
            return [("B", "back"), ("↑↓", "scroll")]
