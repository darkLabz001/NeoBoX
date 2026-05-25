#!/usr/bin/env python3
# neo-name: YouTube
# neo-desc: Watch YouTube (search or URL)
# neo-icon: media
# neo-needs: query
# neo-apt: mpv, yt-dlp, socat
# neo-input: gpio

import os
import signal
import subprocess
import sys
import json
from pathlib import Path

# Paths & Assets
REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "neo" / "keybridge.py"
IPC_SOCKET = "/tmp/mpv-socket"

def list_results(query):
    """Output search results as JSON for the Neo UI to consume."""
    # Format: title ||| id ||| duration_string ||| thumbnail ||| view_count
    # Removed --flat-playlist to ensure we get thumbnails
    template = "%(title)s|||%(id)s|||%(duration_string)s|||%(thumbnail)s|||%(view_count)d"
    cmd = [
        "yt-dlp",
        "--print", template,
        "--no-playlist",
        f"ytsearch10:{query}"
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        results = []
        for line in proc.stdout.strip().split("\n"):
            parts = line.split("|||")
            if len(parts) == 5:
                results.append({
                    "title": parts[0],
                    "id": parts[1],
                    "duration": parts[2],
                    "thumb": parts[3],
                    "views": parts[4],
                    "url": f"https://youtube.com/watch?v={parts[1]}"
                })
        print(json.dumps(results))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

def play(target):
    # mpv config for Pi 3B+
    cmd = [
        "mpv",
        "--fs",
        "--ytdl",
        "--ytdl-format=bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
        "--vo=gpu",
        "--gpu-context=wayland",
        "--ao=pipewire",
        f"--input-ipc-server={IPC_SOCKET}",
        "--hwdec=auto",
        "--cache=yes",
        "--demuxer-max-bytes=100M",
        "--demuxer-readahead-secs=30",
        target
    ]

    print(f"--- Loading YouTube ---")
    print(f"  Target: {target}")
    
    bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "mpv"])
    
    try:
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        env["WAYLAND_DISPLAY"] = env.get("WAYLAND_DISPLAY", "wayland-0")
        subprocess.run(cmd, env=env)
    finally:
        try: bridge.send_signal(signal.SIGTERM)
        except: pass
        subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], capture_output=True, check=False)
        if os.path.exists(IPC_SOCKET):
            try: os.unlink(IPC_SOCKET)
            except: pass

def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    if sys.argv[1] == "--list":
        list_results(" ".join(sys.argv[2:]))
        return

    query = sys.argv[1]
    play(query)

if __name__ == "__main__":
    main()
