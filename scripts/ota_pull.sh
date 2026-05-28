#!/bin/bash
# NeoBoX OTA pull. The previous one died whenever the device had local
# untracked files at paths origin had since started tracking — git pull would
# abort to avoid overwriting them. This handles that and tracked dirty changes:
#
#   1. Auto-detect untracked local files that the incoming pull would overwrite,
#      MOVE them to a timestamped .ota_backup_<ts>/ folder (never delete).
#   2. Stash any tracked dirty changes.
#   3. git pull --ff-only.
#   4. Pop the stash.
#
# Used by Settings -> Update (neo/app.py run_ota).

set -u
cd "$(dirname "$0")/.." || { echo "OTA: cannot cd to repo root"; exit 2; }

echo "Checking for updates..."
if ! git fetch --quiet origin 2>&1; then
    echo "Fetch failed (no internet?)"
    exit 1
fi

BEFORE=$(git rev-parse HEAD)
LATEST=$(git rev-parse origin/master)
if [ "$BEFORE" = "$LATEST" ]; then
    echo "Already up to date."
    exit 0
fi

# 1. Untracked files that the pull would clobber.
conflicts=$(git diff --name-only "$BEFORE" "$LATEST" | while IFS= read -r f; do
    if [ -e "$f" ] && ! git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        printf '%s\n' "$f"
    fi
done)
if [ -n "$conflicts" ]; then
    BK=".ota_backup_$(date +%Y%m%d-%H%M%S)"
    while IFS= read -r f; do
        mkdir -p "$BK/$(dirname "$f")" && mv -- "$f" "$BK/$f" && echo "  preserved: $f"
    done <<< "$conflicts"
    echo "Local copies saved in $BK/ (restore manually if needed)."
fi

# 2. Stash tracked dirty changes.
STASHED=0
if ! git diff --quiet || ! git diff --cached --quiet; then
    if git stash push --quiet -m "ota-$(date +%s)"; then
        STASHED=1
        echo "Stashed local changes."
    fi
fi

# 3. Pull.
if git pull --ff-only --quiet; then
    AFTER=$(git rev-parse --short HEAD)
    echo
    echo "Updated $BEFORE -> $AFTER"
    [ "$STASHED" = "1" ] && git stash pop --quiet 2>/dev/null && echo "Restored stashed changes."
    echo "Press A to apply & restart."
else
    echo
    echo "Pull failed."
    [ "$STASHED" = "1" ] && git stash pop --quiet 2>/dev/null
    exit 1
fi
