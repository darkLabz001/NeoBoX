#!/usr/bin/env python3
# neo-name: CCTV Viewer
# neo-desc: Live traffic cameras (Arlington VA, direct HLS)
# neo-icon: recon
# neo-screen: cctv
# neo-apt: mpv, ffmpeg
# neo-input: gpio
"""Live CCTV gallery. The custom screen (neo/screens/cctv.py) lists the cams and
renders ffmpeg-generated previews; selecting one streams its HLS feed in mpv.

These are public Arlington County, VA traffic cameras (direct .m3u8 — no
scraping / yt-dlp), which is what makes both the previews and playback reliable.

Usage: --list  -> prints the camera JSON;   <m3u8-url> <name>  -> plays a feed."""
import os
import sys
import json
import signal
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "neo" / "keybridge.py"
HLS = "https://itsvideo.arlingtonva.us:8011/live/cam{:02d}.stream/playlist.m3u8"
# Verified-live cam numbers (probed 2026-05-26).
CAMS = [10, 11, 13, 14, 15, 16, 17, 18, 20, 21, 22, 23, 24, 25, 27, 28, 29, 30,
        31, 32, 33, 34, 35, 36, 37, 38, 39, 41, 43, 44, 45, 46, 47, 48, 49, 50,
        51, 52, 53, 54, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 70, 71, 72,
        73, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 90]


def list_cams():
    print(json.dumps([
        {"name": f"Arlington VA - Cam {n:02d}", "url": HLS.format(n), "type": "hls"}
        for n in CAMS
    ]))


def play(url, name):
    print(f"Streaming: {name}")
    bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "mpv"])
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    cmd = ["mpv", "--fs", "--really-quiet",
           "--vo=gpu", "--gpu-context=wayland", "--hwdec=auto", "--ao=pipewire",
           "--cache=yes", "--demuxer-max-bytes=32M",
           f"--force-media-title={name}", url]
    try:
        subprocess.run(cmd, env=env)
    finally:
        try:
            bridge.send_signal(signal.SIGTERM)
        except Exception:
            pass
        subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], capture_output=True)


def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    if sys.argv[1] == "--list":
        list_cams()
        return
    play(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "CCTV")


if __name__ == "__main__":
    main()
