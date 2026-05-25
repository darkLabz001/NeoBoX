#!/usr/bin/env python3
# neo-name: YouTube
# neo-desc: Watch YouTube videos (search or URL)
# neo-icon: media
# neo-needs: query
# neo-apt: mpv, yt-dlp
# neo-input: gpio

import sys
import subprocess
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: youtube.py <search query or URL>")
        sys.exit(1)

    query = sys.argv[1]
    
    # If it doesn't look like a URL, treat it as a search
    if not (query.startswith("http://") or query.startswith("https://") or query.startswith("www.")):
        target = f"ytdl://ytsearch:{query}"
    else:
        target = query

    print(f"Loading: {query}...")
    
    # mpv options for Raspberry Pi:
    # --fs: fullscreen
    # --ytdl: use yt-dlp
    # --vo=gpu: hardware accelerated video output (usually best on Pi with Wayland/DRM)
    # --ao=pipewire: force pipewire audio to match Neo's setup
    cmd = [
        "mpv",
        "--fs",
        "--ytdl",
        "--vo=gpu",
        "--ao=pipewire",
        target
    ]
    
    try:
        subprocess.run(cmd)
    except FileNotFoundError:
        print("Error: 'mpv' or 'yt-dlp' not found.")
        print("Please run 'Settings -> Deps' to install requirements.")
        sys.exit(1)

if __name__ == "__main__":
    main()
