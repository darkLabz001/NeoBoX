#!/usr/bin/env bash
# Sync code to the Pi and restart Neo in the running desktop session (no reboot).
set -euo pipefail
PI="${1:-kali@172.20.10.3}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

rsync -az --delete \
  --exclude '__pycache__' --exclude '.git' --exclude 'previews' --exclude '*.pyc' \
  --exclude 'neo.log' \
  -e "ssh -o StrictHostKeyChecking=accept-new" \
  "$HERE/" "$PI:neo/"

ssh -o StrictHostKeyChecking=accept-new "$PI" '
  export XDG_RUNTIME_DIR=/run/user/$(id -u)
  pkill -f "run.py --mode fullscreen" 2>/dev/null || true
  sleep 1
  # Launch inside the user systemd session so it stays attached to the
  # Wayland compositor (a plain ssh/setsid child loses the connection).
  systemd-run --user --scope -q -- bash "$HOME/neo/launch.sh" >/dev/null 2>&1 &
  sleep 5
  pgrep -f "run.py --mode fullscreen" >/dev/null && echo "Neo restarted on device" || echo "WARN: not running — see ~/neo/neo.log"
'
