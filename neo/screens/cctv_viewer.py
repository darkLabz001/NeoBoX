"""CCTV Viewer screen — Integrated MJPEG/HLS streaming based on BigBox logic."""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime

import pygame
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from . import Screen
from .. import config

class CctvViewerScreen(Screen):
    def __init__(self, app, camera_data: dict):
        super().__init__(app)
        self.cam = camera_data
        self.url = camera_data.get("url")
        self.name = camera_data.get("name", "Unknown Camera")
        
        # State
        self._frame_buffer = deque(maxlen=1)
        self.loading = True
        self.error_msg = None
        self.fps = 0.0
        self.zoom = 1
        self.view_w = config.SCREEN_W - 20
        self.view_h = config.SCREEN_H - 80
        
        self._stop_thread = False
        self._fetch_thread = None
        self._start_stream_thread()

    def _start_stream_thread(self):
        self._stop_thread = False
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
            # skylinewebcams needs resolution too
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
                    time.sleep(2)
        except Exception as e:
            self.error_msg = str(e)

    def on_action(self, action: str):
        if action == "B":
            self._stop_thread = True
            self.app.pop()
        elif action == "UP":
            self.zoom = 2 if self.zoom == 1 else (4 if self.zoom == 2 else 1)

    def update(self, dt: float):
        pass

    def is_animating(self):
        return not self._stop_thread

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, f"LIVE: {self.name[:20]}")
        
        view_rect = pygame.Rect(10, 50, self.view_w, self.view_h)
        pygame.draw.rect(surf, (0, 0, 0), view_rect)
        pygame.draw.rect(surf, theme.color("accent"), view_rect, width=1)
        
        if self.loading:
            font = theme.font("ui")
            txt = font.render("Connecting...", True, theme.color("text_dim"))
            surf.blit(txt, (config.SCREEN_W // 2 - txt.get_width() // 2, config.SCREEN_H // 2))
        elif self.error_msg:
            font = theme.font("ui")
            txt = font.render(f"Error: {self.error_msg[:30]}", True, theme.color("danger"))
            surf.blit(txt, (config.SCREEN_W // 2 - txt.get_width() // 2, config.SCREEN_H // 2))
        elif self._frame_buffer:
            frame = self._frame_buffer[0]
            if self.zoom > 1:
                w, h = frame.get_size()
                cw, ch = w // self.zoom, h // self.zoom
                cx, cy = (w - cw) // 2, (h - ch) // 2
                frame = frame.subsurface((cx, cy, cw, ch))
            
            scaled = pygame.transform.scale(frame, (self.view_w, self.view_h))
            surf.blit(scaled, view_rect.topleft)
            
            # OSD
            small = theme.font("small")
            osd = small.render(f"{self.fps:.1f} FPS | ZOOM: {self.zoom}x", True, theme.color("accent"))
            surf.blit(osd, (view_rect.x + 5, view_rect.bottom - 20))

    def hints(self):
        return [("B", "back"), ("UP", "zoom")]
