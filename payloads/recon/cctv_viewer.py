#!/usr/bin/env python3
# neo-name: CCTV Viewer
# neo-desc: MJPEG stream viewer with zoom/pan and grid mode
# neo-icon: recon
# neo-needs: url
# neo-apt: python3-requests, python3-pil
# neo-input: gpio

import os
import sys
import json
import time
import threading
import io
import re
from datetime import datetime
from pathlib import Path

import pygame
import requests
from PIL import Image, ImageEnhance

# Configuration
WIDTH, HEIGHT = 480, 320
LOOT_DIR = Path.home() / "loot" / "CCTV"
LOOT_DIR.mkdir(parents=True, exist_ok=True)
URLS_FILE = LOOT_DIR / "cctv_live.txt"

ZOOM_LEVELS = [1, 2, 4, 8]
CHUNK_SIZE = 1024 * 16

class CCTVViewer:
    def __init__(self, urls):
        self.cameras = urls # List of (name, url, auth)
        self.cam_idx = 0
        self.running = True
        self.streaming = False
        self.grid_mode = False
        
        self.zoom_idx = 0
        self.pan_x = 0.5
        self.pan_y = 0.5
        
        self.fps = 0.0
        self.status = "Idle"
        self.last_frame = None
        self.frame_lock = threading.Lock()
        
        self.grid_frames = {} # idx -> Surface
        self.grid_lock = threading.Lock()
        
        self.stop_event = threading.Event()
        self.recording = False
        self.rec_file = None
        
        # Pygame setup
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("dejavusansmono", 14)
        self.small_font = pygame.font.SysFont("dejavusansmono", 12)

    def _parse_auth(self, url):
        auth = None
        # Check for user:pass@host
        match = re.match(r"https?://([^/]+)@", url)
        if match:
            creds = match.group(1)
            if ":" in creds:
                user, pw = creds.split(":", 1)
                auth = (user, pw)
                url = url.replace(creds + "@", "")
        return url, auth

    def _stream_worker(self, url, auth):
        self.streaming = True
        self.status = "Connecting..."
        try:
            resp = requests.get(url, auth=auth, stream=True, timeout=10)
            resp.raise_for_status()
            
            buf = bytearray()
            frame_count = 0
            fps_start = time.time()
            
            self.status = "Streaming"
            
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if self.stop_event.is_set() or self.grid_mode:
                    break
                
                if self.recording and self.rec_file:
                    self.rec_file.write(chunk)
                    
                buf.extend(chunk)
                
                while True:
                    start = buf.find(b"\xff\xd8")
                    if start < 0: break
                    end = buf.find(b"\xff\xd9", start + 2)
                    if end < 0: break
                    
                    jpg_data = buf[start:end+2]
                    del buf[:end+2]
                    
                    try:
                        img_io = io.BytesIO(jpg_data)
                        img = pygame.image.load(img_io).convert()
                        
                        # Apply zoom/pan
                        zoom = ZOOM_LEVELS[self.zoom_idx]
                        if zoom > 1:
                            w, h = img.get_size()
                            zw, zh = w // zoom, h // zoom
                            zx = int((w - zw) * self.pan_x)
                            zy = int((h - zh) * self.pan_y)
                            img = img.subsurface((zx, zy, zw, zh))
                        
                        img = pygame.transform.scale(img, (WIDTH, HEIGHT))
                        
                        with self.frame_lock:
                            self.last_frame = img
                            
                        frame_count += 1
                        now = time.time()
                        if now - fps_start >= 1.0:
                            self.fps = round(frame_count / (now - fps_start), 1)
                            frame_count = 0
                            fps_start = now
                            
                    except Exception:
                        pass
                        
                if len(buf) > 1024 * 1024: # Cap buffer
                    buf = bytearray()
                    
        except Exception as e:
            self.status = f"Error: {str(e)[:20]}"
        finally:
            self.streaming = False
            self.status = "Stopped"

    def _grid_worker(self, idx, url, auth):
        try:
            resp = requests.get(url, auth=auth, stream=True, timeout=10)
            buf = bytearray()
            cell_w, cell_h = WIDTH // 2, HEIGHT // 2
            
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if self.stop_event.is_set() or not self.grid_mode:
                    break
                buf.extend(chunk)
                while True:
                    s = buf.find(b"\xff\xd8")
                    if s < 0: break
                    e = buf.find(b"\xff\xd9", s + 2)
                    if e < 0: break
                    jpg = buf[s:e+2]
                    del buf[:e+2]
                    try:
                        img = pygame.image.load(io.BytesIO(jpg)).convert()
                        img = pygame.transform.scale(img, (cell_w, cell_h))
                        with self.grid_lock:
                            self.grid_frames[idx] = img
                    except: pass
                if len(buf) > 512 * 1024: buf = bytearray()
        except: pass

    def start_stream(self):
        self.stop_event.clear()
        self.zoom_idx = 0
        self.pan_x, self.pan_y = 0.5, 0.5
        name, url, raw_auth = self.cameras[self.cam_idx]
        url, auth = self._parse_auth(url)
        threading.Thread(target=self._stream_worker, args=(url, auth), daemon=True).start()

    def start_grid(self):
        self.stop_event.clear()
        self.grid_frames.clear()
        count = min(4, len(self.cameras))
        for i in range(count):
            name, url, raw_auth = self.cameras[i]
            url, auth = self._parse_auth(url)
            threading.Thread(target=self._grid_worker, args=(i, url, auth), daemon=True).start()

    def toggle_recording(self):
        if self.recording:
            self.recording = False
            if self.rec_file:
                self.rec_file.close()
                self.rec_file = None
            return False
        else:
            name = self.cameras[self.cam_idx][0]
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = LOOT_DIR / f"{name}_{ts}.mjpeg"
            try:
                self.rec_file = open(path, "wb")
                self.recording = True
                return True
            except:
                return False

    def draw(self):
        self.screen.fill((10, 5, 10))
        
        if self.grid_mode:
            with self.grid_lock:
                for i in range(min(4, len(self.cameras))):
                    x = (i % 2) * (WIDTH // 2)
                    y = (i // 2) * (HEIGHT // 2)
                    if i in self.grid_frames:
                        self.screen.blit(self.grid_frames[i], (x, y))
                    else:
                        pygame.draw.rect(self.screen, (30, 20, 30), (x, y, WIDTH//2, HEIGHT//2), 1)
                        txt = self.small_font.render("Loading...", True, (100, 100, 100))
                        self.screen.blit(txt, (x + 10, y + HEIGHT//4))
                    
                    name = self.cameras[i][0][:12]
                    n_surf = self.small_font.render(name, True, (0, 255, 0))
                    self.screen.blit(n_surf, (x + 5, y + 5))
            
            hint = self.small_font.render("GRID | Y=Back", True, (150, 150, 150))
            self.screen.blit(hint, (5, HEIGHT - 20))
            
        else:
            with self.frame_lock:
                if self.last_frame:
                    self.screen.blit(self.last_frame, (0, 0))
                else:
                    txt = self.font.render(self.status, True, (150, 150, 150))
                    self.screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2))
            
            # HUD
            name = self.cameras[self.cam_idx][0]
            pygame.draw.rect(self.screen, (0, 0, 0, 150), (0, 0, WIDTH, 24))
            n_surf = self.font.render(name, True, (45, 226, 255))
            self.screen.blit(n_surf, (10, 4))
            
            f_surf = self.font.render(f"{self.fps} FPS", True, (255, 200, 0))
            self.screen.blit(f_surf, (WIDTH - 70, 4))
            
            if self.zoom_idx > 0:
                z_surf = self.font.render(f"{ZOOM_LEVELS[self.zoom_idx]}x", True, (255, 100, 0))
                self.screen.blit(z_surf, (WIDTH - 120, 4))
                
            if self.recording:
                pygame.draw.circle(self.screen, (255, 0, 0), (WIDTH - 85, 12), 4)

            # Help
            hint = self.small_font.render("L/R=Cam  X=Zoom  Y=Grid  A=Rec  B=Exit", True, (100, 100, 100))
            pygame.draw.rect(self.screen, (0, 0, 0, 150), (0, HEIGHT-20, WIDTH, 20))
            self.screen.blit(hint, (10, HEIGHT - 18))

        pygame.display.flip()

    def run(self):
        self.start_stream()
        
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                
                if event.type == pygame.KEYDOWN:
                    # Map Neo Actions
                    if event.key == pygame.K_k or event.key == pygame.K_ESCAPE: # B
                        self.running = False
                    
                    elif event.key == pygame.K_u: # X (Zoom)
                        if not self.grid_mode:
                            self.zoom_idx = (self.zoom_idx + 1) % len(ZOOM_LEVELS)
                            if self.zoom_idx == 0:
                                self.pan_x, self.pan_y = 0.5, 0.5
                                
                    elif event.key == pygame.K_i: # Y (Grid)
                        self.grid_mode = not self.grid_mode
                        self.stop_event.set()
                        time.sleep(0.2)
                        if self.grid_mode:
                            self.start_grid()
                        else:
                            self.start_stream()
                            
                    elif event.key == pygame.K_j or event.key == pygame.K_RETURN: # A (Rec)
                        if not self.grid_mode:
                            self.toggle_recording()
                            
                    elif event.key == pygame.K_LEFT:
                        if self.zoom_idx > 0:
                            self.pan_x = max(0.0, self.pan_x - 0.1)
                        else:
                            self.cam_idx = (self.cam_idx - 1) % len(self.cameras)
                            self.stop_event.set()
                            time.sleep(0.1)
                            self.start_stream()
                            
                    elif event.key == pygame.K_RIGHT:
                        if self.zoom_idx > 0:
                            self.pan_x = min(1.0, self.pan_x + 0.1)
                        else:
                            self.cam_idx = (self.cam_idx + 1) % len(self.cameras)
                            self.stop_event.set()
                            time.sleep(0.1)
                            self.start_stream()
                            
                    elif event.key == pygame.K_UP and self.zoom_idx > 0:
                        self.pan_y = max(0.0, self.pan_y - 0.1)
                    elif event.key == pygame.K_DOWN and self.zoom_idx > 0:
                        self.pan_y = min(1.0, self.pan_y + 0.1)

            self.draw()
            self.clock.tick(30)
            
        self.stop_event.set()
        if self.rec_file: self.rec_file.close()
        pygame.quit()

def main():
    urls = []
    # Try to load from file
    if URLS_FILE.exists():
        with open(URLS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line or "|" not in line: continue
                parts = line.split("|")
                # Format: Name|URL|Auth(optional)
                name = parts[0]
                url = parts[1]
                auth = parts[2] if len(parts) > 2 else None
                urls.append((name, url, auth))
    
    # Add the provided URL if given
    if len(sys.argv) > 1 and sys.argv[1]:
        urls.insert(0, ("Target", sys.argv[1], None))
        
    if not urls:
        print(f"No cameras found. Add to {URLS_FILE} (Name|URL)")
        sys.exit(1)
        
    viewer = CCTVViewer(urls)
    viewer.run()

if __name__ == "__main__":
    main()
