#!/bin/bash
# Neo launcher for the Game HAT (called from labwc autostart).
#
# Safety: if ~/neo/NOAUTOSTART exists, we skip launching and stay on the
# desktop — so a broken build can never lock us out of the device.
[ -f "$HOME/neo/NOAUTOSTART" ] && exit 0

# Brief settle for the compositor + session services (pipewire) to be ready.
sleep 1

cd "$HOME/neo" || exit 0
export SDL_VIDEODRIVER=wayland
# Inherited from the labwc session at boot; default them so a manual/ssh
# relaunch (via systemd --user) still finds the compositor.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

# Game HAT panel is 480x320; its HDMI board only accepts standard modes and
# scales to the panel. Feed it the smallest (640x480) for the sharpest result.
command -v wlr-randr >/dev/null && wlr-randr --output HDMI-A-1 --mode 640x480 2>/dev/null || true

# Route audio to HDMI (the HAT's speakers) at a usable level (amp needs boost).
hdmi_id=$(wpctl status 2>/dev/null | sed -n '/Sinks:/,/Sources:/p' | grep -i hdmi | grep -oE '[0-9]+' | head -1)
if [ -n "$hdmi_id" ]; then
  wpctl set-default "$hdmi_id" 2>/dev/null || true
  wpctl set-mute "$hdmi_id" 0 2>/dev/null || true
  wpctl set-volume "$hdmi_id" 1.3 2>/dev/null || true
fi

# Pin a large audio buffer (quantum). The Pi 3B+ can't reliably keep the tiny
# default buffer (~128 samples, requested by SDL/RetroArch) filled, so the HDMI
# sink underruns constantly -> choppy/crackly audio device-wide (pw-top shows
# climbing ERR/xruns). 2048 (~43ms latency, fine for a handheld) stops it cold.
command -v pw-metadata >/dev/null && \
  pw-metadata -n settings 0 clock.force-quantum 2048 >/dev/null 2>&1 || true

# Ensure Web UI service is running


# Log persists across reboots (unlike /tmp) for debugging.
exec python3 run.py --mode fullscreen --gpio >> "$HOME/neo/neo.log" 2>&1 >> "$HOME/neo/neo.log" 2>&1
