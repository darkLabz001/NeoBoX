"""CCTV Viewer screen — High-tech integrated MJPEG/HLS streaming engine."""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import threading
import time
import random
from collections import deque
from datetime import datetime

import pygame
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from . import Screen
from .. import config

class CctvViewerScreen(Screen):
    def __init__(self, app, cameras: list[dict], index: int):
        super().__init__(app)
        self.cameras = cameras
        self.index = index
        self.cam = cameras[index]
        
        # State
        self._frame_buffer = deque(maxlen=1)
        self.loading = True
        self.error_msg = None
        self.fps = 0.0
        self.zoom = 1
        self.view_w = config.SCREEN_W - 20
        self.view_h = config.SCREEN_H - 80
        
        # FX State
        self._scanline_y = 0
        self._glitch_t = 0
        self._scanlines_surf = self._create_scanlines()
        
        self._stop_thread = False
        self._fetch_thread = None
        self._start_stream_thread()

    def _create_scanlines(self):
        s = pygame.Surface((self.view_w, self.view_h), pygame.SRCALPHA)
        for y in range(0, self.view_h, 2):
            pygame.draw.line(s, (0, 0, 0, 60), (0, y), (self.view_w, y))
        return s

    def _start_stream_thread(self):
        self._stop_thread = False
        self._frame_buffer.clear()
        self.loading = True
        self.error_msg = None
        self.cam = self.cameras[self.index]
        self.url = self.cam.get("url")
        self.name = self.cam.get("name", "Unknown Camera")
        
        if self._fetch_thread and self._fetch_thread.is_alive():
            # Wait briefly or just start a new one if it's daemon
            pass
            
        self._fetch_thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._fetch_thread.start()

    def _hls_loop(self, url) -> None:
        if not shutil.which("ffmpeg"):
            self.error_msg = "ffmpeg not found"
            return

        cmd = [
            "nice", "-n", "10",
            "ffmpeg",
            "-loglevel", "error",
            "-hide_banner",
            "-threads", "1",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-probesize", "32",
            "-analyzeduration", "0",
            "-user_agent", "Mozilla/5.0",
            "-i", url,
            "-vf", f"scale={self.view_w}:{self.view_h}:force_original_aspect_ratio=decrease,"
                   f"pad={self.view_w}:{self.view_h}:(ow-iw)/2:(oh-ih)/2",
            "-r", "12",
            "-q:v", "6",
            "-an",
            "-f", "mjpeg",
            "pipe:1",
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            self.error_msg = f"ffmpeg fail: {e}"
            return

        self.loading = False
        buf = bytearray()
        last_fps_check = time.time()
        frames_this_sec = 0
        try:
            while not self._stop_thread:
                chunk = proc.stdout.read(32768) if proc.stdout else b""
                if not chunk: break
                buf.extend(chunk)
                while True:
                    a = buf.find(b"\xff\xd8")
                    b = buf.find(b"\xff\xd9", a + 2)
                    if a == -1 or b == -1: break
                    jpg = bytes(buf[a:b + 2])
                    del buf[:b + 2]
                    try:
                        raw_surf = pygame.image.load(io.BytesIO(jpg))
                        self._frame_buffer.append(raw_surf)
                        frames_this_sec += 1
                        now = time.time()
                        if now - last_fps_check > 1.0:
                            self.fps = frames_this_sec
                            frames_this_sec = 0
                            last_fps_check = now
                    except: pass
                if len(buf) > 1024 * 1024: buf = bytearray()
        finally:
            proc.terminate()

    def _fetch_loop(self) -> None:
        url = self.url
        if "opentopia.com" in url:
            try:
                r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                m = re.search(r'href="([^"]+)"[^>]*>Host', r.text)
                if m:
                    h = m.group(1).rstrip("/")
                    url = f"{h}/axis-cgi/mjpg/video.cgi" if "/axis-cgi" not in h else h
            except: pass

        if url.lower().split("?", 1)[0].endswith(".m3u8") or "skylinewebcams" in url:
            if "skylinewebcams" in url:
                try:
                    r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                    m = re.search(r'url:\s*["\'](https://[^"\']+\.m3u8)["\']', r.text)
                    if m: url = m.group(1)
                except: pass
            self._hls_loop(url)
            return

        # MJPEG or Snapshot
        try:
            r = requests.get(url, timeout=10, stream=True, verify=False, headers={'User-Agent': 'Mozilla/5.0'})
            ctype = r.headers.get("Content-Type", "").lower()
            if "multipart" in ctype or "mjpeg" in url.lower():
                self.loading = False
                buf = bytearray()
                last_fps_check = time.time()
                frames_this_sec = 0
                for chunk in r.iter_content(chunk_size=32768):
                    if self._stop_thread: break
                    buf.extend(chunk)
                    while True:
                        a = buf.find(b"\xff\xd8")
                        b = buf.find(b"\xff\xd9", a + 2)
                        if a != -1 and b != -1:
                            jpg = bytes(buf[a:b+2])
                            del buf[:b+2]
                            try:
                                raw_surf = pygame.image.load(io.BytesIO(jpg))
                                self._frame_buffer.append(raw_surf)
                                frames_this_sec += 1
                                now = time.time()
                                if now - last_fps_check > 1.0:
                                    self.fps = frames_this_sec
                                    frames_this_sec = 0
                                    last_fps_check = now
                            except: pass
                        else: break
                    if len(buf) > 1024 * 1024: buf = bytearray()
            else:
                # Polling snapshots
                while not self._stop_thread:
                    r = requests.get(url, timeout=5, verify=False, headers={'User-Agent': 'Mozilla/5.0'})
                    if r.status_code == 200:
                        raw_surf = pygame.image.load(io.BytesIO(r.content))
                        self._frame_buffer.append(raw_surf)
                        self.loading = False
                        self.fps = 1.0
                    for _ in range(40): # Sleep 2s but check stop_thread
                        if self._stop_thread: break
                        time.sleep(0.05)
        except Exception as e:
            self.error_msg = str(e)

    def on_action(self, action: str):
        if action == "B":
            self._stop_thread = True
            self.app.pop()
        elif action == "UP":
            self.zoom = 2 if self.zoom == 1 else (4 if self.zoom == 2 else 1)
        elif action == "LEFT":
            self._stop_thread = True
            self.index = (self.index - 1) % len(self.cameras)
            self._start_stream_thread()
        elif action == "RIGHT":
            self._stop_thread = True
            self.index = (self.index + 1) % len(self.cameras)
            self._start_stream_thread()

    def update(self, dt: float):
        self._scanline_y = (self._scanline_y + dt * 60) % self.view_h
        if random.random() < 0.05:
            self._glitch_t = 0.15

    def is_animating(self):
        return True

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, f"REC: {self.name[:24].upper()}")
        
        view_rect = pygame.Rect(10, 50, self.view_w, self.view_h)
        pygame.draw.rect(surf, (0, 0, 0), view_rect)
        pygame.draw.rect(surf, theme.color("accent"), view_rect, width=1)
        
        if self.loading:
            font = theme.font("ui")
            txt = font.render("HANDSHAKING...", True, theme.color("text_dim"))
            surf.blit(txt, (config.SCREEN_W // 2 - txt.get_width() // 2, config.SCREEN_H // 2))
        elif self.error_msg:
            font = theme.font("ui")
            txt = font.render(f"LINK LOSS: {self.error_msg[:30].upper()}", True, theme.color("danger"))
            surf.blit(txt, (config.SCREEN_W // 2 - txt.get_width() // 2, config.SCREEN_H // 2))
        elif self._frame_buffer:
            frame = self._frame_buffer[0]
            if self.zoom > 1:
                w, h = frame.get_size()
                cw, ch = w // self.zoom, h // self.zoom
                cx, cy = (w - cw) // 2, (h - ch) // 2
                frame = frame.subsurface((cx, cy, cw, ch))
            
            scaled = pygame.transform.scale(frame, (self.view_w, self.view_h))
            
            # Glitch effect
            if self._glitch_t > 0:
                self._glitch_t -= 0.016 # Roughly 1/60
                y = random.randint(0, self.view_h - 10)
                h = random.randint(2, 8)
                off = random.randint(-10, 10)
                sub = scaled.subsurface((0, y, self.view_w, h)).copy()
                scaled.blit(sub, (off, y))
            
            surf.blit(scaled, view_rect.topleft)
            
            # Scanlines overlay
            surf.blit(self._scanlines_surf, view_rect.topleft)
            
            # Scanning bar
            sy = view_rect.y + self._scanline_y
            pygame.draw.line(surf, (theme.color("accent").r, theme.color("accent").g, theme.color("accent").b, 100), 
                             (view_rect.x, sy), (view_rect.right, sy), 1)

            # OSD Overlay
            small = theme.font("small")
            accent = theme.color("accent")
            
            # Corners
            L = 15
            c = accent
            r = view_rect
            pygame.draw.lines(surf, c, False, [(r.x+L, r.y), (r.x, r.y), (r.x, r.y+L)], 2)
            pygame.draw.lines(surf, c, False, [(r.right-L, r.y), (r.right, r.y), (r.right, r.y+L)], 2)
            pygame.draw.lines(surf, c, False, [(r.x+L, r.bottom), (r.x, r.bottom), (r.x, r.bottom-L)], 2)
            pygame.draw.lines(surf, c, False, [(r.right-L, r.bottom), (r.right, r.bottom), (r.right, r.bottom-L)], 2)
            
            # Text info
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            surf.blit(small.render(f"CAM_{self.index:02d} | {ts}", True, accent), (view_rect.x + 10, view_rect.y + 10))
            
            fps_col = accent if self.fps > 5 else theme.color("danger")
            surf.blit(small.render(f"SIGNAL: {self.fps:.1f} FPS", True, fps_col), (view_rect.x + 10, view_rect.bottom - 25))
            surf.blit(small.render(f"ZOOM: {self.zoom}X", True, accent), (view_rect.right - 70, view_rect.bottom - 25))
            
            # REC dot
            if int(time.time()) % 2 == 0:
                pygame.draw.circle(surf, theme.color("danger"), (view_rect.right - 15, view_rect.y + 18), 5)
                surf.blit(small.render("REC", True, theme.color("danger")), (view_rect.right - 45, view_rect.y + 10))

    def hints(self):
        return [("B", "back"), ("UP", "zoom"), ("LR", "switch")]
