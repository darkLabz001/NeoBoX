"""Flock Finder — list nearby ALPR/Flock Safety cameras from OpenStreetMap.

The data comes from public OSM tags (`surveillance:type=ALPR`, `camera:type=ALPR`,
or `operator~Flock`), the same source the DeFlock project and EFF Atlas of
Surveillance work with. Use it to know what's deployed in your neighborhood —
don't interfere with the cameras themselves. They are public infrastructure
that the OSM community has voluntarily mapped."""
from __future__ import annotations

import json
import math
import subprocess
import threading
import time
from pathlib import Path

import pygame

from . import Screen
from .. import config
from ..ui import statusbar
from ..ui.listview import ListView


KNOWN_METROS = [
    ("Atlanta, GA",   33.7490,  -84.3880),
    ("Houston, TX",   29.7604,  -95.3698),
    ("Phoenix, AZ",   33.4484, -112.0740),
    ("Memphis, TN",   35.1495,  -90.0490),
    ("Dallas, TX",    32.7767,  -96.7970),
    ("Charlotte, NC", 35.2271,  -80.8431),
    ("Tampa, FL",     27.9506,  -82.4572),
    ("Las Vegas, NV", 36.1699, -115.1398),
]


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class FlockScreen(Screen):
    modal = True
    title = "FLOCK FINDER"

    def __init__(self, app, meta=None):
        super().__init__(app)
        self.meta = meta or {}
        self.metro_idx = 0
        self.location = KNOWN_METROS[self.metro_idx]
        self.results: list[dict] = []
        self.status = "querying"          # querying | ready | error
        self.error = ""
        self._t0 = time.time()
        # list area below the location header, above the hint bar
        top = statusbar.HEIGHT + 58
        bot = config.SCREEN_H - 28
        self.list = ListView(pygame.Rect(10, top, config.SCREEN_W - 20, bot - top), row_h=42)
        self._query()

    # --- query ----------------------------------------------------------
    def _query(self):
        self.status = "querying"
        self._t0 = time.time()
        self.results = []
        self.list.set_items([])
        threading.Thread(target=self._query_thread, daemon=True).start()

    def _query_thread(self):
        name, lat, lon = self.location
        try:
            cmd = ["python3", str(config.PAYLOADS_DIR / "recon" / "flock_finder.py"),
                   "--list", str(lat), str(lon), "20000"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            data = json.loads(proc.stdout or "[]")
            if isinstance(data, dict) and "error" in data:
                self.error = str(data["error"])[:80]
                self.status = "error"
                return
            for d in data:
                d["_dist"] = _haversine_m(lat, lon, d["lat"], d["lon"])
            data.sort(key=lambda d: d["_dist"])
            self.results = data
            self.list.set_items(data)
            self.status = "ready"
        except Exception as exc:
            self.error = str(exc)[:80]
            self.status = "error"

    # --- input ----------------------------------------------------------
    def on_action(self, action: str):
        if self.status == "querying":
            if action in ("B", "EXIT", "MENU"):
                self.app.pop()
            return
        if action == "X":
            self.metro_idx = (self.metro_idx + 1) % len(KNOWN_METROS)
            self.location = KNOWN_METROS[self.metro_idx]
            self._query()
            return
        if action == "Y":   # re-query same location
            self._query()
            return
        r = self.list.on_action(action)
        if r == "back" or action in ("EXIT", "MENU"):
            self.app.pop()

    # --- animation ------------------------------------------------------
    def update(self, dt):
        self.list.update(dt)

    def is_animating(self):
        return self.status == "querying" or self.list.is_animating()

    # --- draw -----------------------------------------------------------
    def draw(self, surf, theme):
        surf.fill(theme.color("bg"))
        self.app.statusbar.draw(surf, theme, self.title)

        small = theme.font("small")
        ui = theme.font("ui")
        accent = theme.color("accent")
        text = theme.color("text")
        dim = theme.color("text_dim")
        danger = theme.color("danger")
        cx = config.SCREEN_W // 2

        # location header
        y = statusbar.HEIGHT + 8
        head = ui.render(f"@ {self.location[0]}", True, accent)
        surf.blit(head, (12, y))
        meta = small.render(
            f"{self.location[1]:.4f}, {self.location[2]:.4f}   ·  20 km radius   ·  OSM (DeFlock-style)",
            True, dim)
        surf.blit(meta, (12, y + 22))
        # underline rule
        pygame.draw.line(surf, accent, (12, y + 42), (config.SCREEN_W - 12, y + 42), 1)

        if self.status == "querying":
            dots = "." * (int((time.time() - self._t0) * 2) % 4)
            t = ui.render(f"Querying OpenStreetMap{dots}", True, dim)
            surf.blit(t, t.get_rect(center=(cx, config.SCREEN_H // 2)))
            return
        if self.status == "error":
            t = small.render(f"Error: {self.error}", True, danger)
            surf.blit(t, (14, statusbar.HEIGHT + 58))
            t2 = small.render("Press Y to retry.", True, dim)
            surf.blit(t2, (14, statusbar.HEIGHT + 78))
            return
        if not self.results:
            t = small.render("No Flock/ALPR cameras tagged in OSM here.", True, dim)
            surf.blit(t, t.get_rect(center=(cx, config.SCREEN_H // 2)))
            t2 = small.render("Press X for another city.", True, dim)
            surf.blit(t2, t2.get_rect(center=(cx, config.SCREEN_H // 2 + 22)))
            return

        # results count chip
        cnt = small.render(f"{len(self.results)} cameras", True, accent)
        surf.blit(cnt, (config.SCREEN_W - cnt.get_width() - 14, y + 24))

        # list
        def _row(surf, theme, rect, item, sel):
            font = theme.font("ui")
            sm = theme.font("small")
            ac = theme.color("accent")
            tx = theme.color("text")
            dm = theme.color("text_dim")
            dist = item["_dist"]
            dstr = f"{dist / 1000:.1f}km" if dist >= 1000 else f"{int(dist)}m"
            ds = font.render(dstr, True, ac if sel else tx)
            surf.blit(ds, (rect.x + 12, rect.centery - ds.get_height() // 2))
            # name / operator
            label = (item.get("name") or item.get("operator") or "ALPR Camera")
            ts = sm.render(label[:34], True, tx if sel else dm)
            surf.blit(ts, (rect.x + 86, rect.y + 6))
            coords = sm.render(f"{item['lat']:.4f}, {item['lon']:.4f}", True, dm)
            surf.blit(coords, (rect.x + 86, rect.y + 22))
            # operator badge right
            op = (item.get("operator") or "")[:12]
            if op:
                col = ac if "flock" in op.lower() else dm
                os_ = sm.render(op, True, col)
                surf.blit(os_, (rect.right - os_.get_width() - 12, rect.centery - os_.get_height() // 2))

        self.list.draw(surf, theme, _row)

    def hints(self):
        if self.status == "querying":
            return [("B", "back")]
        return [("A", "details"), ("X", "city"), ("Y", "refresh"), ("B", "back")]
