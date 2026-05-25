#!/usr/bin/env bash
# Sync the project to the Pi over SSH/rsync.
set -euo pipefail
PI="${1:-kali@172.20.10.3}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
rsync -az --delete \
  --exclude '__pycache__' --exclude '.git' --exclude 'previews' --exclude '*.pyc' \
  -e "ssh -o StrictHostKeyChecking=accept-new" \
  "$HERE/" "$PI:neo/"
echo "synced -> $PI:~/neo"
