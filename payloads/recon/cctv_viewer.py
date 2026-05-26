#!/usr/bin/env python3
# neo-name: CCTV Viewer
# neo-desc: Live CCTV aggregator (FL511, Opentopia, WebcamTaxi)
# neo-icon: recon
# neo-screen: cctv
# neo-apt: python3-requests, python3-pil, mpv, yt-dlp
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

# Configuration
WIDTH, HEIGHT = 480, 320
ZOOM_LEVELS = [1, 2, 4, 8]
CHUNK_SIZE = 1024 * 32
IPC_SOCKET = "/tmp/mpv-cctv-socket"
REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "neo" / "keybridge.py"

# =============================================================================
# API / Scraper Mode
# =============================================================================

def list_cams():
    """Scrape and aggregate live camera feeds."""
    results = []

    # 1. FL511 (ArcGIS API)
    try:
        # Query Florida Traffic Cameras (limit 15 for speed)
        fl_url = "https://services1.arcgis.com/O1Jpc7z9x79mdhjt/arcgis/rest/services/FL511_Traffic_Cameras/FeatureServer/0/query"
        params = {
            "where": "1=1",
            "outFields": "Camera_Name,Video_URL,Image_URL",
            "resultRecordCount": 15,
            "f": "json"
        }
        resp = requests.get(fl_url, params=params, timeout=5)
        data = resp.json()
        for f in data.get("features", []):
            attr = f["attributes"]
            if attr.get("Video_URL"):
                results.append({
                    "name": f"FL: {attr['Camera_Name']}",
                    "thumb": attr.get("Image_URL"),
                    "url": attr["Video_URL"],
                    "type": "hls"
                })
    except Exception as e:
        pass

    # 2. Opentopia (Requested 15516 + others)
    opentopia_cams = [
        ("Nagano, JP", "15516"),
        ("Tokyo, JP", "16031"),
        ("Amsterdam, NL", "10191"),
        ("Paris, FR", "9532")
    ]
    for name, cid in opentopia_cams:
        results.append({
            "name": f"Open: {name}",
            "thumb": f"http://www.opentopia.com/images/cams/{cid}.jpg",
            # Note: Direct MJPEG URLs often change. We'll use the Opentopia proxy if possible,
            # but for this demo we'll target common MJPEG patterns.
            # Real-world: needs a secondary scraper to find the 'host' link.
            "url": f"http://www.opentopia.com/webcam/{cid}", 
            "type": "web" # We'll handle this in the UI
        })

    # 3. WebcamTaxi (Hardcoded stable streams)
    webcam_taxi = [
        ("Times Square, NY", "https://www.youtube.com/watch?v=1-iS7LArMPA"),
        ("Venice, IT", "https://www.youtube.com/watch?v=ph1vpnYIxJk")
    ]
    for name, url in webcam_taxi:
        results.append({
            "name": f"Taxi: {name}",
            "thumb": "recon", # Fallback icon
            "url": url,
            "type": "hls"
        })

    print(json.dumps(results))

# =============================================================================
# MJPEG Engine (Custom Pygame)
# =============================================================================

class MJPEGViewer:
    def __init__(self, url, name="CCTV"):
        self.url = url
        self.name = name
        self.running = True
        self.last_frame = None
        self.frame_lock = threading.Lock()
        self.fps = 0.0
        self.status = "Connecting..."
        self.zoom_idx = 0
        self.pan_x, self.pan_y = 0.5, 0.5
        
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("dejavusansmono", 14)

    def _worker(self):
        try:
            resp = requests.get(self.url, stream=True, timeout=10)
            resp.raise_for_status()
            buf = bytearray()
            fc = 0
            t0 = time.time()
            self.status = "Streaming"
            
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if not self.running: break
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
                        
                        # Zoom
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
                        fc += 1
                        if time.time() - t0 >= 1.0:
                            self.fps = round(fc / (time.time() - t0), 1)
                            fc, t0 = 0, time.time()
                    except: pass
                if len(buf) > 1024*512: buf = bytearray()
        except Exception as e:
            self.status = f"Error: {str(e)[:20]}"

    def run(self):
        threading.Thread(target=self._worker, daemon=True).start()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_k, pygame.K_ESCAPE): self.running = False
                    elif event.key == pygame.K_u: # Zoom
                        self.zoom_idx = (self.zoom_idx + 1) % len(ZOOM_LEVELS)
                    elif event.key == pygame.K_LEFT and self.zoom_idx > 0: self.pan_x = max(0, self.pan_x - 0.1)
                    elif event.key == pygame.K_RIGHT and self.zoom_idx > 0: self.pan_x = min(1, self.pan_x + 0.1)
                    elif event.key == pygame.K_UP and self.zoom_idx > 0: self.pan_y = max(0, self.pan_y - 0.1)
                    elif event.key == pygame.K_DOWN and self.zoom_idx > 0: self.pan_y = min(1, self.pan_y + 0.1)

            self.screen.fill((0, 0, 0))
            with self.frame_lock:
                if self.last_frame: self.screen.blit(self.last_frame, (0, 0))
                else:
                    txt = self.font.render(self.status, True, (150, 150, 150))
                    self.screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2))
            
            # HUD
            pygame.draw.rect(self.screen, (0, 0, 0, 180), (0, 0, WIDTH, 24))
            self.screen.blit(self.font.render(self.name, True, (45, 226, 255)), (10, 4))
            self.screen.blit(self.font.render(f"{self.fps} FPS", True, (255, 200, 0)), (WIDTH-70, 4))
            
            pygame.display.flip()
            self.clock.tick(30)
        pygame.quit()

# =============================================================================
# Main
# =============================================================================

def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    # API Mode
    if sys.argv[1] == "--list":
        list_cams()
        return

    # Play Mode
    target = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "CCTV"
    
    if target.endswith((".m3u8", ".mpd")) or "youtube" in target or "google" in target:
        # HLS / Stream -> use mpv
        print(f"Launching Stream: {name}")
        import subprocess
        import signal
        
        # Start bridge
        bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "mpv"])
        
        cmd = [
            "mpv", "--fs", "--vo=gpu", "--gpu-context=wayland", "--ao=pipewire",
            "--ytdl-format=bestvideo[height<=720]+bestaudio/best[height<=720]",
            target
        ]
        try:
            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = "/run/user/1000"
            env["WAYLAND_DISPLAY"] = "wayland-0"
            subprocess.run(cmd, env=env)
        finally:
            try: bridge.send_signal(signal.SIGTERM)
            except: pass
            subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], capture_output=True, check=False)
    else:
        # Assume MJPEG
        viewer = MJPEGViewer(target, name)
        viewer.run()

if __name__ == "__main__":
    main()
