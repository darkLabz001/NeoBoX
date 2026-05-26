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
    
    # 0. BigBox Verified (High reliability)
    bigbox = [
        ("Avalon Golf", "http://74.95.172.65:8100/axis-cgi/mjpg/video.cgi", "mjpeg"),
        ("Norway Coast", "http://78.31.82.246/mjpg/video.mjpg", "mjpeg"),
        ("Playa Levante", "http://212.170.100.189/mjpg/video.mjpg", "mjpeg"),
        ("Airport USA", "http://199.104.253.4/mjpg/video.mjpg", "mjpeg"),
        ("Madrid, ESP", "http://83.48.75.113:8320/axis-cgi/mjpg/video.cgi", "mjpeg"),
        ("Stelvio Pass", "https://jpeg.popso.it/webcam/webcam_online/stelviolive_05.jpg", "snapshot"),
        ("Fair Harbor", "http://webcam.fairharbormarina.com/nphMotionJpeg?Resolution=640x480", "mjpeg"),
        ("Seattle 1st & Denny", "https://61e0c5d388c2e.streamlock.net:443/live/1_N_Denny_EW.stream/playlist.m3u8", "hls"),
        ("Seattle 3rd & Denny", "https://61e0c5d388c2e.streamlock.net:443/live/3_N_Denny_EW.stream/playlist.m3u8", "hls"),
        ("Seattle Elliott & Broad", "https://61e0c5d388c2e.streamlock.net:443/live/Elliott_Broad_NS.stream/playlist.m3u8", "hls"),
    ]
    for name, url, ctype in bigbox:
        results.append({
            "name": f"Box: {name}",
            "thumb": "recon",
            "url": url, "type": ctype
        })

    # 1. Skyline (Standard world feeds)
    skyline = [
        ("Times Square", "https://www.skylinewebcams.com/en/webcam/united-states/new-york/new-york/times-square.html"),
        ("Venice", "https://www.skylinewebcams.com/en/webcam/italia/veneto/venezia/canal-grande-rialto.html"),
        ("Milan", "https://www.skylinewebcams.com/en/webcam/italia/lombardia/milano/duomo-milano.html"),
        ("Piazza Navona", "https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/piazza-navona.html")
    ]
    for name, url in skyline:
        slug = url.split("/")[-1].replace(".html", "")
        results.append({
            "name": f"Sky: {name}",
            "thumb": f"https://cdn.skylinewebcams.com/thumbs/{slug}.jpg",
            "url": url, "type": "hls"
        })

    # 2. Arlington (Reliable HLS)
    for cid in [10, 11, 20, 21, 25]:
        results.append({
            "name": f"Arlington Cam {cid}",
            "thumb": "recon", 
            "url": f"https://itsvideo.arlingtonva.us:8011/live/cam{cid}.stream/playlist.m3u8",
            "type": "hls"
        })

    # 3. Opentopia (Security feeds)
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
