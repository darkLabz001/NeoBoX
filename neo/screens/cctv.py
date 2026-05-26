"""CCTV Gallery screen — Robust Integrated Version."""
from __future__ import annotations

import json
import subprocess
import threading
import io
import hashlib
import time
from pathlib import Path
from queue import Queue

import pygame
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from . import Screen
from .. import config, assets
from ..ui import statusbar

CCTV_CACHE = config.CACHE_DIR / "cctv_thumbs"

class CctvGalleryScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        CCTV_CACHE.mkdir(parents=True, exist_ok=True)
        self.results = []
        self.index = 0
        self.scroll = 0
        self.target_scroll = 0
        self.loading = True
        self.error = None
        self.thumbs = {} # URL -> Surface
        self._thumb_queue = Queue()
        self._load_data()

    def _load_data(self):
        self.loading = True
        self.error = None
        self.results = []
        def worker():
            try:
                # Use a longer timeout and capture output
                cmd = ["python3", str(config.PAYLOADS_DIR / "recon" / "cctv_viewer.py"), "--list"]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                # Robust extraction: ignore everything before the first [ and after the last ]
                out = proc.stdout.strip()
                start = out.find("[")
                end = out.rfind("]")
                if start != -1 and end != -1:
                    json_str = out[start:end+1]
                    data = json.loads(json_str)
                    self.results = data
                    for item in self.results:
                        turl = item.get("thumb")
                        if turl and turl.startswith("http"):
                            self._request_thumb(turl)
                else:
                    self.error = "No camera data found"
            except Exception as e:
                self.error = "Connection timeout"
            finally:
                self.loading = False
        threading.Thread(target=worker, daemon=True).start()

    def _request_thumb(self, url):
        h = hashlib.md5(url.encode()).hexdigest()
        cache_path = CCTV_CACHE / f"cctv_{h}.jpg"
        def load():
            try:
                if cache_path.exists() and (time.time() - cache_path.stat().st_mtime < 3600):
                    with open(cache_path, "rb") as f: data = f.read()
                else:
                    r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
                    if r.status_code == 200:
                        data = r.content
                        with open(cache_path, "wb") as f: f.write(data)
                    else: return
                self._thumb_queue.put((url, data))
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
                self.app.launch_payload(self._get_meta(), {}, cam["url"], cam["name"])
        elif action == "B":
            self.app.pop()

    def _ensure_visible(self):
        if self.index < self.target_scroll: self.target_scroll = self.index
        elif self.index >= self.target_scroll + 5: self.target_scroll = self.index - 4

    def _get_meta(self):
        return {
            "name": "CCTV Viewer",
            "path": str(config.PAYLOADS_DIR / "recon" / "cctv_viewer.py"),
            "input": "gpio"
        }

    def update(self, dt: float):
        self.scroll += (self.target_scroll - self.scroll) * 0.2
        while not self._thumb_queue.empty():
            url, data = self._thumb_queue.get()
            try:
                img = pygame.image.load(io.BytesIO(data)).convert()
                # Use a cleaner scale for previews
                self.thumbs[url] = pygame.transform.smoothscale(img, (80, 45))
            except: pass

    def is_animating(self):
        return self.loading or abs(self.scroll - self.target_scroll) > 0.01 or not self._thumb_queue.empty()

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "CCTV GALLERY")
        
        font = theme.font("ui")
        small = theme.font("small")
        accent = theme.color("accent")
        text = theme.color("text")
        dim = theme.color("text_dim")

        ry = statusbar.HEIGHT + 10
        area = pygame.Rect(10, ry, config.SCREEN_W - 20, config.SCREEN_H - ry - 28)

        if self.loading:
            txt = font.render("Scraping World Feeds...", True, dim)
            surf.blit(txt, (config.SCREEN_W // 2 - txt.get_width() // 2, ry + 40))
        elif self.error:
            txt = font.render(f"Error: {self.error}", True, theme.color("danger"))
            surf.blit(txt, (config.SCREEN_W // 2 - txt.get_width() // 2, ry + 40))
        elif self.results:
            # Scrollbar
            if len(self.results) > 5:
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
                if sel: pygame.draw.rect(surf, accent, rect, width=1, border_radius=6)
                
                turl = item.get("thumb")
                if turl in self.thumbs:
                    surf.blit(self.thumbs[turl], (rect.x + 4, rect.y + 1))
                else:
                    # Clearer fallback box
                    pygame.draw.rect(surf, (20, 20, 30), (rect.x + 4, rect.y + 3, 80, 40), border_radius=4)
                    icon = assets.load_icon_image("recon", 16)
                    if icon: surf.blit(icon, (rect.x + 36, rect.y + 15))

                name = item["name"]
                if len(name) > 42: name = name[:39] + "..."
                surf.blit(small.render(name, True, text), (rect.x + 90, rect.y + 4))
                
                ctype = item.get('type', 'hls').upper()
                surf.blit(small.render(f"LIVE | {ctype}", True, dim), (rect.x + 90, rect.y + 24))
            
            surf.set_clip(prev_clip)

    def hints(self):
        return [("B", "back"), ("A", "view"), ("↑↓", "nav")]
