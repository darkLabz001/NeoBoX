#!/bin/bash
# Neo launcher for the Game HAT (called from labwc autostart).
#
# Safety: if ~/neo/NOAUTOSTART exists, we skip launching and stay on the
# desktop — so a broken build can never lock us out of the device.
[ -f "$HOME/neo/NOAUTOSTART" ] && exit 0

# Give the Wayland compositor a moment to come up.
sleep 2

cd "$HOME/neo" || exit 0
export SDL_VIDEODRIVER=wayland
# Inherited from the labwc session at boot; default them so a manual/ssh
# relaunch (via systemd --user) still finds the compositor.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

# Game HAT panel is 480x320; its HDMI board only accepts standard modes and
# scales to the panel. Feed it the smallest (640x480) for the sharpest result.
command -v wlr-randr >/dev/null && wlr-randr --output HDMI-A-1 --mode 640x480 2>/dev/null || true
sleep 1

# Log persists across reboots (unlike /tmp) for debugging.
exec python3 run.py --mode fullscreen --gpio >> "$HOME/neo/neo.log" 2>&1
