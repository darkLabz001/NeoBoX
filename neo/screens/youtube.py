"""YouTube search and result screen."""
from __future__ import annotations

import json
import subprocess
import threading
import io

import pygame
import requests

from . import Screen
from .textinput import OnScreenKeyboard
from .. import config
from ..ui import statusbar

def format_views(v):
    try:
        num = int(v)
        if num >= 1_000_000: return f"{num/1_000_000:.1f}M views"
        if num >= 1_000: return f"{num/1_000:.1f}K views"
        return f"{num} views"
    except: return f"{v} views"

class YoutubeSearchScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.results = []
        self.index = 0
        self.scroll = 0
        self.query = ""
        self.loading = False
        self.error = None
        self.thumbs = {} # URL -> Surface
        
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
                video = self.results[self.index]
                self.app.launch_payload(self._get_meta(), {}, video["url"])
            else:
                self._open_search()
        elif action == "X":
            self._open_search()
        elif action == "B":
            self.app.pop()

    def _ensure_visible(self):
        # Visible area can show ~4 results
        if self.index < self.scroll:
            self.scroll = self.index
        elif self.index >= self.scroll + 4:
            self.scroll = self.index - 3

    def _get_meta(self):
        return {
            "name": "YouTube",
            "path": str(config.PAYLOADS_DIR / "media" / "youtube.py"),
            "input": "gpio"
        }

    def _open_search(self):
        def on_done(val):
            self.app.pop()
            if val: self._search(val)
        self.app.push(OnScreenKeyboard(self.app, "YouTube Search", on_done, initial=self.query))

    def _search(self, query):
        self.query = query
        self.loading = True
        self.error = None
        self.results = []
        self.index = 0
        self.scroll = 0
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        try:
            cmd = ["python3", str(config.PAYLOADS_DIR / "media" / "youtube.py"), "--list", query]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(proc.stdout)
            if isinstance(data, dict) and "error" in data:
                self.error = data["error"]
            else:
                self.results = data
                for item in self.results:
                    self._load_thumb(item["thumb"])
        except Exception as e:
            self.error = str(e)
        finally:
            self.loading = False

    def _load_thumb(self, url):
        def load():
            try:
                resp = requests.get(url, timeout=5)
                f = io.BytesIO(resp.content)
                img = pygame.image.load(f)
                img = pygame.transform.smoothscale(img, (80, 45))
                self.thumbs[url] = img
            except: pass
        threading.Thread(target=load, daemon=True).start()

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "YOUTUBE")
        
        font = theme.font("ui")
        small = theme.font("small")
        accent = theme.color("accent")
        
        # Search bar
        sbox = pygame.Rect(10, statusbar.HEIGHT + 8, config.SCREEN_W - 20, 30)
        pygame.draw.rect(surf, theme.color("tile"), sbox, border_radius=6)
        if not self.results and not self.loading:
            pygame.draw.rect(surf, accent, sbox, width=1, border_radius=6)
            
        qtext = self.query or "Press X to search..."
        qsurf = font.render(qtext, True, theme.color("text") if self.query else theme.color("text_dim"))
        surf.blit(qsurf, (sbox.x + 10, sbox.y + 5))

        # Results
        ry = sbox.bottom + 6
        if self.loading:
            txt = font.render("Searching...", True, theme.color("text_dim"))
            surf.blit(txt, (config.SCREEN_W // 2 - txt.get_width() // 2, ry + 40))
        elif self.error:
            txt = small.render(f"Error: {self.error}", True, theme.color("danger"))
            surf.blit(txt, (10, ry))
        elif self.results:
            visible = self.results[self.scroll : self.scroll + 5]
            for i, item in enumerate(visible):
                real_idx = self.scroll + i
                rect = pygame.Rect(10, ry + i * 50, config.SCREEN_W - 20, 46)
                sel = (real_idx == self.index)
                bg = theme.color("tile_sel") if sel else theme.color("tile")
                pygame.draw.rect(surf, bg, rect, border_radius=6)
                if sel:
                    pygame.draw.rect(surf, accent, rect, width=1, border_radius=6)
                
                # Thumbnail
                turl = item["thumb"]
                if turl in self.thumbs:
                    surf.blit(self.thumbs[turl], (rect.x + 4, rect.y + 1))
                else:
                    pygame.draw.rect(surf, theme.color("bg"), (rect.x + 4, rect.y + 3, 80, 40), border_radius=4)
                
                # Title
                title = item["title"]
                if len(title) > 42: title = title[:39] + "..."
                tsurf = small.render(title, True, theme.color("text"))
                surf.blit(tsurf, (rect.x + 90, rect.y + 4))
                
                # Info: Duration | Views
                info = f"{item['duration']}  •  {format_views(item['views'])}"
                isurf = small.render(info, True, theme.color("text_dim"))
                surf.blit(isurf, (rect.x + 90, rect.y + 24))

    def hints(self):
        h = [("B", "back"), ("X", "search")]
        if self.results: h.append(("A", "play"))
        return h
