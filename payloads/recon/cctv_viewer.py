#!/usr/bin/env python3
# neo-name: CCTV Viewer
# neo-desc: Port of KTOx_Pi high-perf CCTV viewer
# neo-icon: recon
# neo-screen: cctv
# neo-apt: python3-requests, python3-pil, mpv, libturbojpeg0
# neo-input: gpio

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import sys
import json
import time
import threading
import io
import re
import subprocess
from pathlib import Path
from collections import deque

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Hardware acceleration check
try:
    from turbojpeg import TurboJPEG
    jpeg = TurboJPEG()
except:
    jpeg = None

# Configuration
WIDTH, HEIGHT = 480, 320
CHUNK_SIZE = 1024 * 32
REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "neo" / "keybridge.py"

# =============================================================================
# Scraper / API Mode (Ported from KTOx style)
# =============================================================================

def list_cams():
    """Aggregated camera list with KTOx reliability."""
    results = []
    
    # 1. Skyline (Standard world feeds)
    skyline = [
        ("Times Square", "https://www.skylinewebcams.com/en/webcam/united-states/new-york/new-york/times-square.html"),
        ("Venice", "https://www.skylinewebcams.com/en/webcam/italia/veneto/venezia/canal-grande-rialto.html"),
        ("Milan", "https://www.skylinewebcams.com/en/webcam/italia/lombardia/milano/duomo-milano.html")
    ]
    for name, url in skyline:
        slug = url.split("/")[-1].replace(".html", "")
        results.append({
            "name": f"Sky: {name}",
            "thumb": f"https://cdn.skylinewebcams.com/thumbs/{slug}.jpg",
            "url": url,
            "type": "hls"
        })

    # 2. Arlington (Reliable HLS cluster)
    for cid in [10, 11, 20, 21, 25]:
        results.append({
            "name": f"Arlington Cam {cid}",
            "thumb": "recon",
            "url": f"https://itsvideo.arlingtonva.us:8011/live/cam{cid}.stream/playlist.m3u8",
            "type": "hls"
        })

    # 3. Opentopia (Requested Nagano 15516 cam)
    opentopia = [
        ("Nagano (JP)", "15516"),
        ("Tokyo (JP)", "16031"),
        ("Zurich (CH)", "12519")
    ]
    for name, cid in opentopia:
        results.append({
            "name": f"Open: {name}",
            "thumb": f"https://www.opentopia.com/images/cams/{cid}.jpg",
            "url": f"http://www.opentopia.com/webcam/{cid}",
            "type": "mjpeg"
        })

    sys.stdout.write(json.dumps(results))
    sys.stdout.flush()

# =============================================================================
# Playback Engine (Core Port)
# =============================================================================

class KTOxViewer:
    def __init__(self, url, name="CCTV"):
        import pygame
        self.url = url
        self.name = name
        self.running = True
        self.frame_queue = deque(maxlen=1)
        self.status = "Port connecting..."
        self.fps = 0
        self.zoom = 1
        self.pan_x, self.pan_y = 0.5, 0.5
        
        pygame.init()
        # Pi 3B+ Wayland reliability
        try: self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
        except: self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("dejavusansmono", 14)

    def _resolve_url(self, url):
        """KTOx style host resolver."""
        if "opentopia.com" in url:
            try:
                r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                m = re.search(r'href="([^"]+)"[^>]*>Host', r.text)
                if m:
                    h = m.group(1).rstrip("/")
                    return f"{h}/axis-cgi/mjpg/video.cgi" if "/axis-cgi" not in h else h
            except: pass
        if "skylinewebcams" in url:
            try:
                r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                m = re.search(r'url:\s*["\'](https://[^"\']+\.m3u8)["\']', r.text)
                if m: return m.group(1)
            except: pass
        return url

    def _stream_worker(self):
        import pygame
        target = self._resolve_url(self.url)
        self.status = "Streaming"
        try:
            r = requests.get(target, stream=True, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            r.raise_for_status()
            buf = bytearray()
            fc = 0
            t0 = time.time()
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                if not self.running: break
                buf.extend(chunk)
                while True:
                    s = buf.find(b"\xff\xd8")
                    if s < 0: break
                    e = buf.find(b"\xff\xd9", s + 2)
                    if e < 0: break
                    jpg_data = buf[s:e+2]
                    del buf[:e+2]
                    try:
                        # Use TurboJPEG if available
                        if jpeg:
                            img_np = jpeg.decode(jpg_data)
                            # Convert BGR (TurboJPEG) to RGB (Pygame)
                            img_np = img_np[:, :, ::-1]
                            surf = pygame.surfarray.make_surface(img_np.swapaxes(0, 1))
                        else:
                            surf = pygame.image.load(io.BytesIO(jpg_data)).convert()
                        
                        # Post-process (Zoom/Scale)
                        if self.zoom > 1:
                            w, h = surf.get_size()
                            zw, zh = w // self.zoom, h // self.zoom
                            zx = int((w - zw) * self.pan_x)
                            zy = int((h - zh) * self.pan_y)
                            surf = surf.subsurface((zx, zy, zw, zh))
                        
                        surf = pygame.transform.scale(surf, (WIDTH, HEIGHT))
                        self.frame_queue.append(surf)
                        fc += 1
                        if time.time() - t0 >= 1.0:
                            self.fps = fc
                            fc, t0 = 0, time.time()
                    except: pass
                if len(buf) > 1024*1024: buf = bytearray()
        except Exception as e:
            self.status = f"Port Error: {str(e)[:20]}"

    def run(self):
        import pygame
        threading.Thread(target=self._stream_worker, daemon=True).start()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_k, pygame.K_ESCAPE): self.running = False
                    elif event.key == pygame.K_u: self.zoom = 2 if self.zoom == 1 else (4 if self.zoom == 2 else 1)
                    elif event.key == pygame.K_LEFT and self.zoom > 1: self.pan_x = max(0, self.pan_x - 0.1)
                    elif event.key == pygame.K_RIGHT and self.zoom > 1: self.pan_x = min(1, self.pan_x + 0.1)
                    elif event.key == pygame.K_UP and self.zoom > 1: self.pan_y = max(0, self.pan_y - 0.1)
                    elif event.key == pygame.K_DOWN and self.zoom > 1: self.pan_y = min(1, self.pan_y + 0.1)

            self.screen.fill((5, 5, 10))
            if self.frame_queue:
                self.screen.blit(self.frame_queue[0], (0, 0))
            else:
                txt = self.font.render(self.status, True, (100, 100, 110))
                self.screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2))
            
            # KTOx Style HUD
            pygame.draw.rect(self.screen, (0, 0, 0, 150), (0, 0, WIDTH, 22))
            self.screen.blit(self.font.render(f"LIVE: {self.name}", True, (0, 255, 0)), (10, 3))
            self.screen.blit(self.font.render(f"{self.fps} FPS", True, (255, 255, 0)), (WIDTH - 60, 3))
            if self.zoom > 1:
                self.screen.blit(self.font.render(f"{self.zoom}x", True, (255, 100, 0)), (WIDTH - 100, 3))
            
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
    
    # HLS detection for world feeds
    if ".m3u8" in target or "skylinewebcams" in target or "arlingtonva.us" in target:
        import signal
        bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "mpv"])
        # Optimized MPV for Pi 3B+
        cmd = ["mpv", "--fs", "--vo=gpu", "--gpu-context=wayland", "--ao=pipewire",
               "--tls-verify=no", "--cache=yes", "--demuxer-max-bytes=100M",
               "--ytdl-format=bestvideo[height<=720]+bestaudio/best[height<=720]", target]
        try:
            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = "/run/user/1000"; env["WAYLAND_DISPLAY"] = "wayland-0"
            subprocess.run(cmd, env=env)
        finally:
            try: bridge.send_signal(signal.SIGTERM)
            except: pass
            subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], capture_output=True, check=False)
    else:
        # High-perf MJPEG port
        viewer = KTOxViewer(target, name)
        viewer.run()

if __name__ == "__main__":
    main()
