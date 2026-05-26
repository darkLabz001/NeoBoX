"""Pwnagotchi-style WPA handshake harvester that runs *inside* NeoBoX without
taking the device over: NeoBoX keeps the screen and the buttons, the onboard
radio keeps you connected, and capture runs on the USB monitor-mode adapter
(wlan1) underneath via hcxdumptool. Loot (PMKIDs / handshakes) lands in ~/loot
as .pcapng for offline cracking.

The face is a sprite animation that reacts to the capture: it wakes up looking
at the gear, hunts (intense/excited) while it sees traffic, flashes "!" then
grins when it grabs a handshake/PMKID, and dozes off (Zzz) when the air is quiet.

Only run this against networks you own or are explicitly authorized to test."""
from __future__ import annotations

import glob
import math
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import pygame

from . import Screen
from .. import config
from ..ui import statusbar

LOOT = Path.home() / "loot"
SPR_DIR = config.ASSETS_DIR / "sprites" / "pwn"
MOODS = ("intense", "excited", "calm", "alert", "sad", "happy", "look", "sleep")
OPEN_EYED = {"intense", "excited", "alert", "sad", "look"}   # moods that "blink"
FACE_H = 104


def capture_iface() -> str | None:
    """The USB monitor-mode adapter: a wifi interface that is NOT the onboard
    brcmfmac radio and NOT the one carrying our default route (connectivity).
    Returns None on a machine with only its connectivity radio (e.g. a laptop),
    so this can never hijack the interface you're online through."""
    conn_if = ""
    try:
        r = subprocess.run(["ip", "route", "show", "default"],
                           capture_output=True, text=True, timeout=3).stdout
        m = re.search(r"dev (\S+)", r)
        conn_if = m.group(1) if m else ""
    except Exception:
        pass
    for net in sorted(glob.glob("/sys/class/net/*")):
        name = os.path.basename(net)
        if name == conn_if or not os.path.exists(net + "/phy80211"):
            continue
        drv = ""
        if os.path.exists(net + "/device/driver"):
            drv = os.path.realpath(net + "/device/driver")
        if "brcmfmac" in drv:          # onboard Pi radio — connectivity only
            continue
        return name
    return None


def _load_sprites() -> dict:
    out = {}
    for m in MOODS:
        p = SPR_DIR / f"{m}.png"
        if not p.exists():
            continue
        try:
            img = pygame.image.load(str(p)).convert_alpha()
            s = FACE_H / img.get_height()
            out[m] = pygame.transform.scale(img, (int(img.get_width() * s), FACE_H))
        except Exception:
            pass
    return out


class PwnagotchiScreen(Screen):
    modal = True   # own MENU/EXIT so B/EXIT cleanly stops capture

    def __init__(self, app, meta=None):
        super().__init__(app)
        self.meta = meta or {}
        self.title = "PWNAGOTCHI"
        self.iface = capture_iface()
        self.sprites = _load_sprites()
        self.pmkid = self.handshakes = self.packets = 0
        self.t0 = time.time()
        self._prev_packets = 0
        self._last_loot = 0
        self._last_activity = self.t0       # last time we saw new packets
        self._happy_until = 0.0
        self._alert_until = 0.0
        self._hop_t = -9.0
        self._stop = threading.Event()
        self.pcap = None
        if self.iface:
            self.status = "waking"
            LOOT.mkdir(parents=True, exist_ok=True)
            self.pcap = LOOT / time.strftime("pwn-%Y%m%d-%H%M%S.pcapng")
            threading.Thread(target=self._run, daemon=True).start()
        else:
            self.status = "no adapter"

    # --- background capture --------------------------------------------
    def _run(self):
        subprocess.run(["sudo", "-n", "nmcli", "dev", "set", self.iface, "managed", "no"],
                       capture_output=True)
        proc = subprocess.Popen(
            ["sudo", "-n", "hcxdumptool", "-i", self.iface, "-w", str(self.pcap), "-F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        self.status = "hunting"
        self._last_activity = time.time()
        while not self._stop.wait(5.0):        # poll counts ~every 5s
            self._update_counts()
        subprocess.run(["sudo", "-n", "pkill", "-TERM", "-f", "hcxdumptool"], capture_output=True)
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        subprocess.run(["sudo", "-n", "nmcli", "dev", "set", self.iface, "managed", "yes"],
                       capture_output=True)

    def _update_counts(self):
        if not (self.pcap and self.pcap.exists()):
            return
        try:
            out = subprocess.run(["hcxpcapngtool", str(self.pcap)],
                                 capture_output=True, text=True, timeout=25).stdout
        except Exception:
            return

        def n(pat):
            m = re.search(pat + r"[^:]*:\s*(\d+)", out)
            return int(m.group(1)) if m else 0

        self.pmkid = n(r"PMKID\(s\)")
        self.handshakes = n(r"EAPOL pairs")
        self.packets = n(r"packets inside")
        now = time.time()
        if self.packets > self._prev_packets:
            self._last_activity = now          # there's traffic -> stay awake/hunting
        self._prev_packets = self.packets
        loot = self.pmkid + self.handshakes
        if loot > self._last_loot:             # GOT ONE -> "!" then a grin + hop
            self._alert_until = now + 0.7
            self._happy_until = now + 5.0
            self._hop_t = now
        self._last_loot = loot

    # --- mood / animation ----------------------------------------------
    def _mood(self, now: float) -> str:
        if not self.iface:
            return "sad"
        if self.status == "waking":
            return "look"
        if now < self._alert_until:
            return "alert"
        if now < self._happy_until:
            return "happy"
        quiet = now - self._last_activity
        if quiet < 9:                          # actively seeing traffic
            return "excited" if int(now * 0.7) % 2 else "intense"
        if quiet < 60:
            return "calm"
        return "sleep"

    # --- input ----------------------------------------------------------
    def on_action(self, action):
        if action in ("B", "EXIT", "MENU"):
            self._stop.set()
            self.app.pop()

    def is_animating(self):
        return True        # the face is always alive (bob + blink)

    # --- draw -----------------------------------------------------------
    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, self.title)
        top = statusbar.HEIGHT + 6
        panel = pygame.Surface((config.SCREEN_W - 32, config.SCREEN_H - top - 30), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 160))
        surf.blit(panel, (16, top))
        pygame.draw.rect(surf, theme.color("accent"),
                         (16, top, config.SCREEN_W - 32, config.SCREEN_H - top - 30),
                         width=1, border_radius=10)

        ui, small = theme.font("ui"), theme.font("small")
        accent, text, dim = theme.color("accent"), theme.color("text"), theme.color("text_dim")
        cx = config.SCREEN_W // 2
        now = time.time()
        t = now - self.t0
        mood = self._mood(now)

        # --- animated face ---
        frame = mood
        if mood in OPEN_EYED and (t % 3.0) < 0.16:     # blink
            frame = "calm"
        bob = round(math.sin(t * 2.6) * 3)             # gentle float
        hop = -9 if (now - self._hop_t) < 0.4 else 0   # little jump on a capture
        spr = self.sprites.get(frame) or self.sprites.get(mood)
        face_cy = top + 64
        if spr:
            surf.blit(spr, spr.get_rect(center=(cx, face_cy + bob + hop)))
        else:                                          # fallback if sprites missing
            surf.blit(ui.render(mood, True, accent),
                      ui.render(mood, True, accent).get_rect(center=(cx, face_cy)))

        st = small.render(self.status.upper(), True, dim)
        surf.blit(st, st.get_rect(center=(cx, face_cy + FACE_H // 2 + 8)))

        if not self.iface:
            m = small.render("Plug in the USB monitor-mode adapter.", True, dim)
            surf.blit(m, m.get_rect(center=(cx, face_cy + FACE_H // 2 + 30)))
            return

        # --- stats ---
        y = face_cy + FACE_H // 2 + 26
        for label, val in (("HANDSHAKES", self.handshakes), ("PMKIDs", self.pmkid),
                           ("packets", self.packets)):
            surf.blit(small.render(label, True, dim), (44, y + 2))
            vs = ui.render(str(val), True, accent if val else text)
            surf.blit(vs, (config.SCREEN_W - 44 - vs.get_width(), y))
            y += 22
        up = int(t)
        info = f"{self.iface}   up {up // 60}:{up % 60:02d}   ->  ~/loot"
        surf.blit(small.render(info, True, dim),
                  small.render(info, True, dim).get_rect(center=(cx, config.SCREEN_H - 40)))

    def hints(self):
        return [("B", "stop & exit")]
