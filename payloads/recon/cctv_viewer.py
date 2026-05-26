#!/usr/bin/env python3
# neo-name: CCTV Viewer
# neo-desc: Live CCTV aggregator (FL511, Skyline, Opentopia)
# neo-icon: recon
# neo-screen: cctv
# neo-apt: python3-requests, python3-pil, mpv, yt-dlp
# neo-input: gpio

import os
import sys
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

def resolve_skyline_direct(url):
    """Fast manual scraper for SkylineWebcams m3u8 links."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        match = re.search(r'url:\s*["\'](https://[^"\']+\.m3u8)["\']', resp.text)
        if match: return match.group(1)
    except: pass
    return url

def resolve_opentopia(url):
    """Resolve Opentopia host URL to direct MJPEG stream."""
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

def list_cams():
    """Scrape and aggregate live camera feeds."""
    results = []
    headers = {'User-Agent': 'Mozilla/5.0'}

    # 1. SkylineWebcams
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

    # 2. Arlington VA
    for cid in [10, 11, 13, 14, 15, 20, 21, 25]:
        results.append({
            "name": f"Arlington Cam {cid}",
            "thumb": "recon",
            "url": f"https://itsvideo.arlingtonva.us:8011/live/cam{cid}.stream/playlist.m3u8",
            "type": "hls"
        })

    # 3. FL511
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

    # 4. Opentopia
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
# Main Playback
# =============================================================================

def main():
    if len(sys.argv) < 2: sys.exit(1)
    if sys.argv[1] == "--list":
        list_cams()
        return

    target = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "CCTV"
    
    # Resolve custom web URLs to direct streams
    if "skylinewebcams" in target:
        target = resolve_skyline_direct(target)
    elif "opentopia.com" in target:
        target = resolve_opentopia(target)

    print(f"--- Loading Feed: {name} ---")
    
    # Use MPV for EVERYTHING. It's the most robust player on the Pi.
    # Handles HLS, MJPEG, and direct streams with GPU acceleration.
    import signal
    bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "mpv"])
    
    cmd = [
        "mpv", 
        "--fs", 
        "--vo=gpu", 
        "--gpu-context=wayland", 
        "--ao=pipewire",
        "--tls-verify=no", 
        "--cache=yes", 
        "--demuxer-max-bytes=100M",
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

if __name__ == "__main__":
    main()
