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
import time
from pathlib import Path

# Paths & Assets
REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "neo" / "keybridge.py"
IPC_SOCKET = "/tmp/mpv-socket"

def main():
    if len(sys.argv) < 2:
        print("Usage: youtube.py <query>")
        sys.exit(1)

    query = sys.argv[1]
    target = f"ytdl://ytsearch:{query}" if not query.startswith(("http", "www")) else query

    # mpv config for Pi 3B+ (DRM/GBM is smoothest, but gpu-context=wayland works in Neo labwc)
    cmd = [
        "mpv",
        "--fs",
        "--ytdl",
        "--vo=gpu",
        "--gpu-context=wayland",
        "--ao=pipewire",
        f"--input-ipc-server={IPC_SOCKET}",
        # Pi Performance tweaks:
        "--hwdec=auto",
        "--cache=yes",
        "--demuxer-max-bytes=50M",
        "--demuxer-readahead-secs=20",
        target
    ]

    print(f"--- Loading YouTube ---")
    print(f"  Target: {query}")
    print(f"  Controls: D-pad=Seek  A=Play/Pause  B=Back/Quit")
    
    # Start the key bridge so Game HAT buttons act as keys for mpv
    # mpv defaults: Arrows = seek, Space (A) = pause, q (B) = quit
    bridge = subprocess.Popen(["sudo", "-n", "python3", str(BRIDGE), "mpv"])
    
    try:
        # We use env to ensure mpv finds the Wayland display Neo is using
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        env["WAYLAND_DISPLAY"] = env.get("WAYLAND_DISPLAY", "wayland-0")
        
        subprocess.run(cmd, env=env)
    finally:
        # Clean up bridge
        try:
            bridge.send_signal(signal.SIGTERM)
        except: pass
        subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], 
                       capture_output=True, check=False)
        if os.path.exists(IPC_SOCKET):
            try: os.unlink(IPC_SOCKET)
            except: pass

if __name__ == "__main__":
    main()
