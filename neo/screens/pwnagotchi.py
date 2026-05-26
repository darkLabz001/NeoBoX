"""Pwnagotchi-style WPA handshake harvester that runs *inside* NeoBoX without
taking the device over: NeoBoX keeps the screen and the buttons, the onboard
radio keeps you connected, and capture runs on the USB monitor-mode adapter
(wlan1) underneath via hcxdumptool. Loot (PMKIDs / handshakes) lands in ~/loot
as .pcapng for offline cracking.

Only run this against networks you own or are explicitly authorized to test."""
from __future__ import annotations

import glob
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from . import Screen
from .. import config

LOOT = Path.home() / "loot"

FACES = {            # mood -> kaomoji (ASCII so any font renders it)
    "boot":  "(-_-)",
    "hunt":  "(o_o)",
    "happy":  "(^o^)",
    "dead":  "(x_x)",
}


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


class PwnagotchiScreen(Screen):
    modal = True   # own MENU/EXIT so B/EXIT cleanly stops capture

    def __init__(self, app, meta=None):
        super().__init__(app)
        self.meta = meta or {}
        self.title = "PWNAGOTCHI"
        self.iface = capture_iface()
        self.pmkid = self.handshakes = self.packets = 0
        self.t0 = time.time()
        self._last_loot = 0
        self._happy_until = 0.0
        self._stop = threading.Event()
        self.pcap = None
        if self.iface:
            self.status, self.face = "waking", "boot"
            LOOT.mkdir(parents=True, exist_ok=True)
            self.pcap = LOOT / time.strftime("pwn-%Y%m%d-%H%M%S.pcapng")
            threading.Thread(target=self._run, daemon=True).start()
        else:
            self.status, self.face = "no adapter", "dead"

    # --- background capture --------------------------------------------
    def _run(self):
        # Keep NetworkManager off the capture interface, then let hcxdumptool
        # (which sets its own monitor mode) harvest into the pcapng.
        subprocess.run(["sudo", "-n", "nmcli", "dev", "set", self.iface, "managed", "no"],
                       capture_output=True)
        proc = subprocess.Popen(
            ["sudo", "-n", "hcxdumptool", "-i", self.iface, "-w", str(self.pcap), "-F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        self.status, self.face = "hunting", "hunt"
        while not self._stop.wait(6.0):        # poll counts ~every 6s
            self._update_counts()
        # tear down: hcxdumptool runs as root, so kill it explicitly, then hand
        # the interface back to NetworkManager.
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
        loot = self.pmkid + self.handshakes
        if loot > self._last_loot:
            self._happy_until = time.time() + 4
        self._last_loot = loot

    # --- input ----------------------------------------------------------
    def on_action(self, action):
        if action in ("B", "EXIT", "MENU"):
            self._stop.set()            # capture thread tears everything down
            self.app.pop()

    def update(self, dt):
        if self.iface and self.status == "hunting":
            self.face = "happy" if time.time() < self._happy_until else "hunt"

    # --- draw -----------------------------------------------------------
    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, self.title)
        big, ui, small = theme.font("title"), theme.font("ui"), theme.font("small")
        accent, text, dim = theme.color("accent"), theme.color("text"), theme.color("text_dim")
        cx = config.SCREEN_W // 2

        fs = big.render(FACES.get(self.face, "(o_o)"), True, accent)
        surf.blit(fs, fs.get_rect(center=(cx, 80)))
        st = ui.render(self.status.upper(), True, dim)
        surf.blit(st, st.get_rect(center=(cx, 112)))

        if not self.iface:
            m = small.render("Plug in the USB monitor-mode adapter.", True, dim)
            surf.blit(m, m.get_rect(center=(cx, 150)))
            return

        for label, val in (("HANDSHAKES", self.handshakes), ("PMKIDs", self.pmkid),
                           ("packets seen", self.packets)):
            y = 144 + (("HANDSHAKES", "PMKIDs", "packets seen").index(label)) * 26
            surf.blit(small.render(label, True, dim), (44, y + 2))
            vs = ui.render(str(val), True, accent if val else text)
            surf.blit(vs, (config.SCREEN_W - 44 - vs.get_width(), y))

        up = int(time.time() - self.t0)
        info = f"{self.iface}  up {up // 60}:{up % 60:02d}  ->  ~/loot"
        isf = small.render(info, True, dim)
        surf.blit(isf, isf.get_rect(center=(cx, config.SCREEN_H - 34)))

    def hints(self):
        return [("B", "stop & exit")]
