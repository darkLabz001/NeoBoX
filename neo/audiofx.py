"""UI sound effects (pygame.mixer) and system volume control (wpctl).

Audio routes to whatever the default sink is — launch.sh points that at HDMI,
which on the Game HAT feeds the front speakers.
"""
from __future__ import annotations

import re
import subprocess

import pygame

from . import config

_SOUND_NAMES = ("move", "select", "back", "launch", "boot")


class Sfx:
    def __init__(self, enabled: bool = True, volume: float = 0.55):
        self.ok = False
        self.sounds: dict = {}
        if not enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            for name in _SOUND_NAMES:
                p = config.ASSETS_DIR / "sounds" / f"{name}.wav"
                if p.exists():
                    snd = pygame.mixer.Sound(str(p))
                    snd.set_volume(volume)
                    self.sounds[name] = snd
            self.ok = True
        except Exception as exc:
            print(f"[sfx] disabled: {exc}")

    def play(self, name):
        if self.ok and name in self.sounds:
            try:
                self.sounds[name].play()
            except Exception:
                pass


# --- system volume via wpctl ------------------------------------------
def _hdmi_sink_id():
    try:
        out = subprocess.run(["wpctl", "status"], capture_output=True, text=True,
                             timeout=2).stdout
        in_sinks = False
        for line in out.splitlines():
            if "Sinks:" in line:
                in_sinks = True
                continue
            if "Sources:" in line:
                in_sinks = False
            if in_sinks and "hdmi" in line.lower():
                nums = re.findall(r"\d+", line)
                if nums:
                    return nums[0]
    except Exception:
        pass
    return None


def get_volume() -> float | None:
    sid = _hdmi_sink_id()
    if sid is None:
        return None
    try:
        out = subprocess.run(["wpctl", "get-volume", sid], capture_output=True,
                             text=True, timeout=2).stdout
        m = re.search(r"([\d.]+)", out)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def set_volume(v: float):
    sid = _hdmi_sink_id()
    if sid is None:
        return
    v = max(0.0, min(1.5, v))
    try:
        subprocess.run(["wpctl", "set-mute", sid, "0"], timeout=2)
        subprocess.run(["wpctl", "set-volume", sid, f"{v:.2f}"], timeout=2)
    except Exception:
        pass
