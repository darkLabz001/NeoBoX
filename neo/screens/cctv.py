"""CCTV gallery: lists live traffic cams and shows a preview frame for each
(grabbed from the stream with ffmpeg, cached). Selecting one plays its HLS feed
full-screen in mpv. Previews + playback use the same direct .m3u8, so if a cam
plays, its preview works too."""
from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import time
from pathlib import Path

import pygame

from . import Screen
from .. import config
from ..ui import statusbar

THUMB_DIR = config.CACHE_DIR / "cctv_thumbs"
ROW_H = 50
THUMB_W, THUMB_H = 84, 47
MAX_INFLIGHT = 2          # concurrent ffmpeg preview grabs


class CctvGalleryScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.results = []
        self.index = 0
        self.scroll = 0.0
        self.target_scroll = 0.0
        self.loading = True
        self.error = None
        self.thumbs: dict[str, pygame.Surface] = {}
        self._pending: set[str] = set()
        self._inflight = 0
        self._lock = threading.Lock()
        self._load_data()

    # --- data -----------------------------------------------------------
    def _load_data(self):
        def worker():
            try:
                cmd = ["python3", str(config.PAYLOADS_DIR / "recon" / "cctv_viewer.py"), "--list"]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                data = json.loads(proc.stdout) if proc.stdout.strip() else []
                if data:
                    self.results = data
                else:
                    self.error = "No camera data"
            except Exception as e:
                self.error = f"Load error: {e}"
            finally:
                self.loading = False
        threading.Thread(target=worker, daemon=True).start()

    # --- previews (ffmpeg frame grab, lazy + cached) -------------------
    def _ensure_thumb(self, url):
        with self._lock:
            if url in self.thumbs or url in self._pending or self._inflight >= MAX_INFLIGHT:
                return
            self._pending.add(url)
            self._inflight += 1
        threading.Thread(target=self._grab, args=(url,), daemon=True).start()

    def _grab(self, url):
        try:
            cache = THUMB_DIR / f"{hashlib.md5(url.encode()).hexdigest()}.jpg"
            if not (cache.exists() and cache.stat().st_size > 0):
                THUMB_DIR.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-rw_timeout", "15000000",
                     "-i", url, "-frames:v", "1", "-vf", f"scale={THUMB_W}:-1", str(cache)],
                    capture_output=True, timeout=25)
            if cache.exists() and cache.stat().st_size > 0:
                img = pygame.image.load(str(cache))
                self.thumbs[url] = pygame.transform.smoothscale(img, (THUMB_W, THUMB_H))
        except Exception:
            pass
        finally:
            with self._lock:
                self._pending.discard(url)
                self._inflight -= 1

    # --- input ----------------------------------------------------------
    def on_action(self, action: str):
        if self.loading or not self.results:
            if action == "B":
                self.app.pop()
            return
        if action == "UP":
            self.index = (self.index - 1) % len(self.results)
            self._ensure_visible()
        elif action == "DOWN":
            self.index = (self.index + 1) % len(self.results)
            self._ensure_visible()
        elif action == "L":
            self.index = max(0, self.index - 5); self._ensure_visible()
        elif action == "R":
            self.index = min(len(self.results) - 1, self.index + 5); self._ensure_visible()
        elif action == "A":
            cam = self.results[self.index]
            self.app.launch_payload(self._meta(), {}, cam["url"], cam["name"])
        elif action == "B":
            self.app.pop()

    def _ensure_visible(self):
        if self.index < self.target_scroll:
            self.target_scroll = self.index
        elif self.index >= self.target_scroll + 5:
            self.target_scroll = self.index - 4

    def _meta(self):
        return {"name": "CCTV Viewer", "input": "gpio",
                "path": str(config.PAYLOADS_DIR / "recon" / "cctv_viewer.py")}

    def update(self, dt):
        self.scroll += (self.target_scroll - self.scroll) * 0.25
        if abs(self.scroll - self.target_scroll) < 0.01:
            self.scroll = self.target_scroll

    def is_animating(self):
        return self.loading or abs(self.scroll - self.target_scroll) > 0.01 \
            or self._inflight > 0 or bool(self._pending)

    # --- draw -----------------------------------------------------------
    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "CCTV")
        font, small = theme.font("ui"), theme.font("small")
        accent, text, dim = theme.color("accent"), theme.color("text"), theme.color("text_dim")
        ry = statusbar.HEIGHT + 8
        area = pygame.Rect(8, ry, config.SCREEN_W - 16, config.SCREEN_H - ry - 26)

        if self.loading:
            t = font.render("Loading cameras" + "." * (int(time.time() * 2) % 4), True, dim)
            surf.blit(t, t.get_rect(center=area.center))
            return
        if self.error:
            surf.blit(small.render(self.error, True, theme.color("danger")), (10, ry))
            return

        visible = max(1, area.height // ROW_H)
        surf.set_clip(area)
        for i, item in enumerate(self.results):
            iy = int(ry + (i - self.scroll) * ROW_H)
            if iy < ry - ROW_H or iy > area.bottom:
                continue
            sel = (i == self.index)
            rect = pygame.Rect(8, iy, area.width, ROW_H - 4)
            pygame.draw.rect(surf, theme.color("tile_sel") if sel else theme.color("tile"),
                             rect, border_radius=6)
            if sel:
                pygame.draw.rect(surf, accent, rect, width=1, border_radius=6)
            # preview (lazy ffmpeg grab)
            self._ensure_thumb(item["url"])
            tr = pygame.Rect(rect.x + 4, rect.y + (ROW_H - 4 - THUMB_H) // 2, THUMB_W, THUMB_H)
            thumb = self.thumbs.get(item["url"])
            if thumb:
                surf.blit(thumb, tr)
            else:
                pygame.draw.rect(surf, theme.color("bg"), tr, border_radius=3)
                d = small.render("..." if item["url"] in self._pending else "CAM", True, dim)
                surf.blit(d, d.get_rect(center=tr.center))
            pygame.draw.rect(surf, dim, tr, width=1, border_radius=3)
            # name + status
            name = item["name"][:34]
            surf.blit(font.render(name, True, text), (tr.right + 10, rect.y + 6))
            surf.blit(small.render(f"{item['type'].upper()}  •  LIVE", True,
                                   accent if sel else dim), (tr.right + 10, rect.y + 26))
        surf.set_clip(None)

        # scrollbar
        if len(self.results) > visible:
            bh = max(12, int(area.height * visible / len(self.results)))
            by = ry + int((area.height - bh) * (self.scroll / max(1, len(self.results) - visible)))
            pygame.draw.rect(surf, accent, (config.SCREEN_W - 6, by, 3, bh), border_radius=2)

    def hints(self):
        return [("A", "watch"), ("B", "back"), ("LR", "jump")]
