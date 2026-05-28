#!/bin/bash
# NeoBoX OTA. Tarball-then-reset strategy: nothing local is ever merged into
# the new code, so there is no possible conflict path that can leave broken
# files behind (the last OTA aborted with `<<<<<<< Updated upstream` markers
# in app.py and bricked the device — that can't happen here).
#
#   1. git fetch.
#   2. Nothing-to-do shortcut: same head AND clean tree -> "Already up to date".
#   3. Tar every locally-modified + untracked-non-ignored file into
#      .ota_backup_<ts>/local_changes.tar.gz   (nothing is ever deleted).
#   4. git reset --hard origin/master.   (no merge => no conflict.)
#
# Restore from a tarball: `tar -xzf .ota_backup_<ts>/local_changes.tar.gz`.
set -u
cd "$(dirname "$0")/.." || { echo "OTA: cannot cd to repo root"; exit 2; }

# Per-device files that must NEVER be lost across an OTA — copied aside before
# the reset and put right back. Keep this list short; it's not a substitute
# for proper config storage, just a safety net for per-device secrets.
PRESERVE=(
    "config/wigle.json"     # WiGLE API key — does not rotate
    "certs/cert.pem"        # device-specific HTTPS cert
    "certs/key.pem"         # private key
)

echo "Checking for updates..."
if ! git fetch --quiet origin 2>&1; then
    echo "Fetch failed (no internet?)"
    exit 1
fi

BEFORE=$(git rev-parse HEAD)
LATEST=$(git rev-parse origin/master)

# Already in sync AND clean? Nothing to do.
if [ "$BEFORE" = "$LATEST" ] && git diff --quiet && git diff --cached --quiet \
   && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "Already up to date."
    exit 0
fi

# 1. Tarball anything local that isn't in origin/master, so it can never be lost.
BK=".ota_backup_$(date +%Y%m%d-%H%M%S)"
{
    git diff --name-only HEAD 2>/dev/null
    git diff --name-only --cached 2>/dev/null
    git ls-files --others --exclude-standard 2>/dev/null
} | grep -vE '^(\.ota_backup_|loot/)' | sort -u > /tmp/.ota_manifest.$$ || true

if [ -s /tmp/.ota_manifest.$$ ]; then
    mkdir -p "$BK"
    cp /tmp/.ota_manifest.$$ "$BK/manifest.txt"
    if tar --ignore-failed-read -czf "$BK/local_changes.tar.gz" \
            -T "$BK/manifest.txt" 2>/dev/null && [ -s "$BK/local_changes.tar.gz" ]; then
        n=$(wc -l < "$BK/manifest.txt")
        echo "Saved $n local file(s) -> $BK/local_changes.tar.gz"
    else
        rm -rf "$BK"
    fi
fi
rm -f /tmp/.ota_manifest.$$

# 2. Copy preserve-list files aside so the reset can't touch them.
PRESERVE_DIR=$(mktemp -d -t neo-ota-preserve.XXXXXX)
for f in "${PRESERVE[@]}"; do
    if [ -e "$f" ]; then
        mkdir -p "$PRESERVE_DIR/$(dirname "$f")"
        cp -p "$f" "$PRESERVE_DIR/$f"
    fi
done

# 3. Hard reset to origin. There is no merge, so no conflict is possible.
if ! git reset --hard "$LATEST" --quiet; then
    echo "Reset failed."
    rm -rf "$PRESERVE_DIR"
    exit 1
fi

# 4. Put the preserved files back.
for f in "${PRESERVE[@]}"; do
    if [ -e "$PRESERVE_DIR/$f" ]; then
        mkdir -p "$(dirname "$f")"
        cp -p "$PRESERVE_DIR/$f" "$f"
    fi
done
rm -rf "$PRESERVE_DIR"

AFTER=$(git rev-parse --short HEAD)
if [ "$BEFORE" = "$LATEST" ]; then
    echo "Working tree cleaned (already at $AFTER)."
else
    echo "Updated $(echo "$BEFORE" | cut -c1-7) -> $AFTER"
fi
echo
echo "Press A to apply & restart."
