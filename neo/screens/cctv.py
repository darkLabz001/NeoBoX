"""CCTV Gallery screen."""
from __future__ import annotations

import json
import subprocess
import threading
import io
import hashlib
from pathlib import Path

import pygame
import requests

from . import Screen
from .. import config
from ..ui import statusbar

YT_CACHE = config.CACHE_DIR / "yt_thumbs"

class CctvGalleryScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.results = []
        self.index = 0
        self.scroll = 0
        self.target_scroll = 0
        self.loading = True
        self.error = None
        self.thumbs = {} # URL -> Surface
        self._load_data()

    def _load_data(self):
        def worker():
            try:
                cmd = ["python3", str(config.PAYLOADS_DIR / "recon" / "cctv_viewer.py"), "--list"]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                data = json.loads(proc.stdout)
                self.results = data
                for item in self.results:
                    if item["thumb"] and item["thumb"] != "recon":
                        self._load_thumb(item["thumb"])
            except Exception as e:
                self.error = str(e)
            finally:
                self.loading = False
        threading.Thread(target=worker, daemon=True).start()

    def _load_thumb(self, url):
        h = hashlib.md5(url.encode()).hexdigest()
        cache_path = YT_CACHE / f"cctv_{h}.jpg"
        def load():
            try:
                if cache_path.exists():
                    img = pygame.image.load(str(cache_path))
                else:
                    resp = requests.get(url, timeout=5)
                    with open(cache_path, "wb") as f:
                        f.write(resp.content)
                    img = pygame.image.load(io.BytesIO(resp.content))
                img = pygame.transform.smoothscale(img, (80, 45))
                self.thumbs[url] = img
            except: pass
        threading.Thread(target=load, daemon=True).start()

    def on_action(self, action: str):
        if self.loading: return
        if action == "UP":
            if self.results: 
                self.index = (self.index - 1) % len(self.results)
                self._ensure_visible()
        elif action == "DOWN":
            if self.results: 
                self.index = (self.index + 1) % len(self.results)
                self._ensure_visible()
        elif action == "A":
            if self.results:
                cam = self.results[self.index]
                # Pass both URL and Name
                self.app.launch_payload(self._get_meta(), {}, cam["url"], cam["name"])
        elif action == "B":
            self.app.pop()

    def _ensure_visible(self):
        if self.index < self.target_scroll:
            self.target_scroll = self.index
        elif self.index >= self.target_scroll + 5:
            self.target_scroll = self.index - 4

    def _get_meta(self):
        return {
            "name": "CCTV Viewer",
            "path": str(config.PAYLOADS_DIR / "recon" / "cctv_viewer.py"),
            "input": "gpio"
        }

    def update(self, dt: float):
        self.scroll += (self.target_scroll - self.scroll) * 0.2

    def is_animating(self):
        return self.loading or abs(self.scroll - self.target_scroll) > 0.01

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "CCTV VIEWER")
        
        font = theme.font("ui")
        small = theme.font("small")
        accent = theme.color("accent")
        text = theme.color("text")
        dim = theme.color("text_dim")

        ry = statusbar.HEIGHT + 10
        area = pygame.Rect(10, ry, config.SCREEN_W - 20, config.SCREEN_H - ry - 28)

        if self.loading:
            txt = font.render("Scraping Live Feeds...", True, dim)
            surf.blit(txt, (config.SCREEN_W // 2 - txt.get_width() // 2, ry + 40))
        elif self.error:
            txt = small.render(f"Error: {self.error}", True, theme.color("danger"))
            surf.blit(txt, (10, ry))
        elif self.results:
            # Scrollbar
            pygame.draw.rect(surf, theme.color("tile"), (config.SCREEN_W - 8, ry, 4, area.height), border_radius=2)
            scroll_h = max(10, (5 / len(self.results)) * area.height)
            scroll_y = ry + (self.scroll / len(self.results)) * area.height
            pygame.draw.rect(surf, accent, (config.SCREEN_W - 8, scroll_y, 4, scroll_h), border_radius=2)

            prev_clip = surf.get_clip()
            surf.set_clip(area)
            for i, item in enumerate(self.results):
                iy = ry + (i - self.scroll) * 50
                if iy < ry - 50 or iy > area.bottom: continue
                
                rect = pygame.Rect(10, iy, area.width - 6, 46)
                sel = (i == self.index)
                bg = theme.color("tile_sel") if sel else theme.color("tile")
                pygame.draw.rect(surf, bg, rect, border_radius=6)
                if sel:
                    pygame.draw.rect(surf, accent, rect, width=1, border_radius=6)
                
                # Thumbnail
                turl = item["thumb"]
                if turl in self.thumbs:
                    surf.blit(self.thumbs[turl], (rect.x + 4, rect.y + 1))
                else:
                    # Procedural placeholder
                    pygame.draw.rect(surf, theme.color("bg"), (rect.x + 4, rect.y + 3, 80, 40), border_radius=4)
                    icon = self.app.theme.color("accent")
                    pygame.draw.circle(surf, icon, (rect.x + 44, rect.y + 23), 4)

                # Title
                name = item["name"]
                if len(name) > 42: name = name[:39] + "..."
                tsurf = small.render(name, True, text)
                surf.blit(tsurf, (rect.x + 90, rect.y + 4))
                
                # Type / Status
                info = f"Type: {item['type'].upper()} | Status: LIVE"
                isurf = small.render(info, True, dim)
                surf.blit(isurf, (rect.x + 90, rect.y + 24))
            
            surf.set_clip(prev_clip)

    def hints(self):
        return [("B", "back"), ("A", "view")]
