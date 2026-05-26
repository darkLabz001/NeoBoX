#!/usr/bin/env python3
# neo-name: CCTV Viewer
# neo-desc: Live CCTV aggregator (FL511, Skyline, Opentopia)
# neo-icon: recon
# neo-screen: cctv
# neo-apt: python3-requests, python3-pil, mpv, yt-dlp
# neo-input: gpio

import os
# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import sys
import json
import time
import threading
import io
import re
import subprocess
from pathlib import Path

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Configuration
WIDTH, HEIGHT = 480, 320
ZOOM_LEVELS = [1, 2, 4, 8]
CHUNK_SIZE = 1024 * 32
REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "neo" / "keybridge.py"

# =============================================================================
# Scraper / API Mode
# =============================================================================

def resolve_skyline_direct(url):
    """Fast manual scraper for SkylineWebcams m3u8 links."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        # Skyline encodes their stream URL in a 'url:' field in the JS
        match = re.search(r'url:\s*["\'](https://[^"\']+\.m3u8)["\']', resp.text)
        if match:
            return match.group(1)
    except: pass
    return url

def list_cams():
    """Scrape and aggregate live camera feeds."""
    results = []
    headers = {'User-Agent': 'Mozilla/5.0'}

    # 1. SkylineWebcams (Fast manual resolution)
    skyline_cams = [
        ("Times Square, NY", "https://www.skylinewebcams.com/en/webcam/united-states/new-york/new-york/times-square.html"),
        ("Milan Cathedral, IT", "https://www.skylinewebcams.com/en/webcam/italia/lombardia/milano/duomo-milano.html"),
        ("Piazza Navona, Rome", "https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/piazza-navona.html"),
        ("Grand Canal, Venice", "https://www.skylinewebcams.com/en/webcam/italia/veneto/venezia/canal-grande-rialto.html")
    ]
    
    for name, url in skyline_cams:
        slug = url.split("/")[-1].replace(".html", "")
        results.append({
            "name": f"Sky: {name}",
            "thumb": f"https://cdn.skylinewebcams.com/thumbs/{slug}.jpg",
            "url": url,
            "type": "hls"
        })

    # 2. Arlington VA (High reliability HLS)
    for cid in [10, 11, 13, 14, 15, 20, 21, 25]:
        results.append({
            "name": f"Arlington {cid}",
            "thumb": "recon",
            "url": f"https://itsvideo.arlingtonva.us:8011/live/cam{cid}.stream/playlist.m3u8",
            "type": "hls"
        })

    # 3. FL511 (Florida DOT)
    try:
        fl_url = "https://services1.arcgis.com/0MSEUqKaxRlEPjhp/arcgis/rest/services/FL511_Traffic_Cameras/FeatureServer/0/query"
        params = {"where": "1=1", "outFields": "CameraName,VideoURL,SnapshotURL", "resultRecordCount": 10, "f": "json"}
        resp = requests.get(fl_url, params=params, timeout=5, verify=False, headers=headers)
        data = resp.json()
        for f in data.get("features", []):
            attr = f["attributes"]
            vurl = attr.get("VideoURL")
            if vurl:
                results.append({
                    "name": f"FL: {attr.get('CameraName', 'Cam')}",
                    "thumb": attr.get("SnapshotURL"),
                    "url": vurl,
                    "type": "hls"
                })
    except: pass

    # 4. Opentopia (Security feeds)
    opentopia_cams = [
        ("Nagano, JP", "15516"),
        ("Tokyo, JP", "16031"),
        ("Amsterdam, NL", "10191"),
        ("Paris, FR", "9532")
    ]
    for name, cid in opentopia_cams:
        results.append({
            "name": f"Open: {name}",
            "thumb": f"https://www.opentopia.com/images/cams/{cid}.jpg",
            "url": f"http://www.opentopia.com/webcam/{cid}", 
            "type": "mjpeg"
        })

    sys.stdout.write(json.dumps(results))
    sys.stdout.flush()

# =============================================================================
# Playback Engine
# =============================================================================

def resolve_opentopia(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        match = re.search(r'href="([^"]+)"[^>]*>Host', resp.text)
        if match:
            hurl = match.group(1).rstrip("/")
            if "/axis-cgi" not in hurl: hurl += "/axis-cgi/mjpg/video.cgi"
            return hurl
    except: pass
    return url

class MJPEGViewer:
    def __init__(self, url, name="CCTV"):
        import pygame
        self.url = url
        self.name = name
        self.running = True
        self.last_frame = None
        self.frame_lock = threading.Lock()
        self.fps = 0.0
        self.status = "Initializing..."
        self.zoom_idx = 0
        self.pan_x, self.pan_y = 0.5, 0.5
        
        pygame.init()
        try: self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
        except: self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("dejavusansmono", 14)

    def _worker(self):
        import pygame
        target = self.url
        if "opentopia.com" in target:
            self.status = "Resolving Host..."
            target = resolve_opentopia(target)
            
        self.status = "Opening Stream..."
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(target, stream=True, timeout=15, headers=headers)
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
                        zoom = ZOOM_LEVELS[self.zoom_idx]
                        if zoom > 1:
                            w, h = img.get_size()
                            zw, zh = w // zoom, h // zoom
                            zx = int((w - zw) * self.pan_x)
                            zy = int((h - zh) * self.pan_y)
                            img = img.subsurface((zx, zy, zw, zh))
                        img = pygame.transform.scale(img, (WIDTH, HEIGHT))
                        with self.frame_lock: self.last_frame = img
                        fc += 1
                        if time.time() - t0 >= 1.0:
                            self.fps = round(fc / (time.time() - t0), 1)
                            fc, t0 = 0, time.time()
                    except: pass
                if len(buf) > 1024*1024: buf = bytearray()
        except Exception as e:
            self.status = f"Err: {str(e)[:25]}"

    def run(self):
        import pygame
        threading.Thread(target=self._worker, daemon=True).start()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_k, pygame.K_ESCAPE): self.running = False
                    elif event.key == pygame.K_u: self.zoom_idx = (self.zoom_idx + 1) % len(ZOOM_LEVELS)
                    elif event.key == pygame.K_LEFT and self.zoom_idx > 0: self.pan_x = max(0, self.pan_x - 0.1)
                    elif event.key == pygame.K_RIGHT and self.zoom_idx > 0: self.pan_x = min(1, self.pan_x + 0.1)
                    elif event.key == pygame.K_UP and self.zoom_idx > 0: self.pan_y = max(0, self.pan_y - 0.1)
                    elif event.key == pygame.K_DOWN and self.zoom_idx > 0: self.pan_y = min(1, self.pan_y + 0.1)

            self.screen.fill((10, 5, 10))
            with self.frame_lock:
                if self.last_frame: self.screen.blit(self.last_frame, (0, 0))
                else:
                    txt = self.font.render(self.status, True, (150, 150, 150))
                    self.screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2))
            
            pygame.draw.rect(self.screen, (0, 0, 0, 180), (0, 0, WIDTH, 24))
            self.screen.blit(self.font.render(self.name, True, (45, 226, 255)), (10, 4))
            self.screen.blit(self.font.render(f"{self.fps} FPS", True, (255, 200, 0)), (WIDTH-70, 4))
            pygame.display.flip()
            self.clock.tick(30)
        pygame.quit()

def main():
    if len(sys.argv) < 2: sys.exit(1)
    if sys.argv[1] == "--list":
        list_cams()
        return

    target = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "CCTV"
    
    # Fast resolution for Skyline
    if "skylinewebcams" in target:
        print(f"Resolving {name}...")
        target = resolve_skyline_direct(target)

    # Use mpv for HLS
    if target.endswith((".m3u8", ".mpd")) or "youtube" in target or "google" in target or ".ts" in target:
        print(f"Launching HLS Stream: {name}")
        import signal
        bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "mpv"])
        
        # mpv flags: --tls-verify=no to handle Arlington's TLS errors
        cmd = ["mpv", "--fs", "--vo=gpu", "--gpu-context=wayland", "--ao=pipewire",
               "--tls-verify=no", "--cache=yes", "--demuxer-max-bytes=100M",
               "--ytdl-format=bestvideo[height<=720]+bestaudio/best[height<=720]", target]
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
