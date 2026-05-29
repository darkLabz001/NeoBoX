#!/usr/bin/env python3
# neo-name: CCTV Viewer
# neo-desc: Live CCTV (Skyline, Arlington, Opentopia)
# neo-icon: recon
# neo-screen: cctv
# neo-apt: python3-requests, python3-pil, mpv, libturbojpeg0
# neo-input: gpio

import os
import sys

# SUPPRESS ALL OUTPUT FOR --list
if "--list" in sys.argv:
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
    sys.stderr = open(os.devnull, 'w')

import json
import time
import re
import subprocess
from pathlib import Path

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Configuration
REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "neo" / "keybridge.py"

# =============================================================================
# Scraper / API Mode
# =============================================================================

def list_cams():
    """Aggregated camera list."""
    results = []
    
    # BigBox Verified — every URL below was live-tested on the device
    # 2026-05-29 and rendered actual frames in the viewer. The previous
    # list also had Fair Harbor, three Seattle DOT cams, four Skyline
    # entries, and three Opentopia cams; all 11 were dead (hosts gone or
    # the resolver-page format changed). Removed rather than shipped
    # as broken-on-open feeds. Add new ones only after live-testing.
    bigbox = [
        ("Avalon Golf",   "http://74.95.172.65:8100/axis-cgi/mjpg/video.cgi", "mjpeg"),
        ("Norway Coast",  "http://78.31.82.246/mjpg/video.mjpg", "mjpeg"),
        ("Playa Levante", "http://212.170.100.189/mjpg/video.mjpg", "mjpeg"),
        ("Airport USA",   "http://199.104.253.4/mjpg/video.mjpg", "mjpeg"),
        ("Madrid, ESP",   "http://83.48.75.113:8320/axis-cgi/mjpg/video.cgi", "mjpeg"),
        ("Stelvio Pass",  "https://jpeg.popso.it/webcam/webcam_online/stelviolive_05.jpg", "snapshot"),
    ]
    for name, url, ctype in bigbox:
        results.append({
            "name": f"Box: {name}",
            "thumb": "recon",
            "url": url, "type": ctype
        })

    # Arlington VA traffic cams — public HLS, live-tested 2026-05-29.
    # Takes ~20-25 s for ffmpeg to surface the first frame on Pi 3B+;
    # the screen shows "HANDSHAKING..." until then.
    for cid in [10, 11, 20, 21, 25]:
        results.append({
            "name": f"Arlington Cam {cid}",
            "thumb": "recon",
            "url": f"https://itsvideo.arlingtonva.us:8011/live/cam{cid}.stream/playlist.m3u8",
            "type": "hls"
        })

    # Output ONLY JSON
    sys.stdout = sys.__stdout__
    print(json.dumps(results))
    sys.stdout.flush()

# =============================================================================
# Playback Engine
# =============================================================================

def resolve_url(url):
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

def main():
    if len(sys.argv) < 2: sys.exit(1)
    if sys.argv[1] == "--list":
        list_cams()
        return

    target = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "CCTV"
    
    # Resolve to direct stream
    target = resolve_url(target)

    # Use mpv for robust playback
    import signal
    subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], capture_output=True)
    bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "mpv"])
    
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    env["WAYLAND_DISPLAY"] = "wayland-0"
    
    cmd = ["mpv", "--fs", "--vo=gpu", "--gpu-context=wayland", "--ao=pipewire",
           "--tls-verify=no", "--cache=yes", "--demuxer-max-bytes=100M",
           "--ytdl-format=bestvideo[height<=720]+bestaudio/best[height<=720]", target]
    
    try:
        subprocess.run(cmd, env=env)
    finally:
        try: bridge.kill()
        except: pass
        subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], capture_output=True)

if __name__ == "__main__":
    main()
