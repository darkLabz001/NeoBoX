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
try:
    import requests
except Exception:
    requests = None     # falls back to a metro list if requests is missing

from . import Screen
from .. import config
from ..ui import statusbar
from ..ui.listview import ListView


# Fallback list if the phone-GPS link isn't connected. X cycles through these
# *after* "Here" so the default behaviour is always "scan where I am right now".
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


def _read_phone_gps() -> tuple[float, float, float] | None:
    """Returns (lat, lon, accuracy_m) from the NeoBoX web server's /api/gps,
    which the phone's mobile.html page pushes to over Socket.IO. None if the
    server isn't running, the phone hasn't connected yet, or GPS is 0/0."""
    if requests is None:
        return None
    try:
        r = requests.get("http://127.0.0.1:8888/api/gps", timeout=2)
        if r.status_code == 200:
            g = r.json().get("gps", {})
            lat = float(g.get("lat") or 0)
            lon = float(g.get("lon") or 0)
            acc = float(g.get("acc") or 0)
            if lat != 0.0 or lon != 0.0:
                return (lat, lon, acc)
    except Exception:
        pass
    return None


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
        # Locations to cycle through. Index 0 is "Here" (live phone GPS); the
        # rest are fallback metros for when GPS isn't connected. X cycles
        # forward through the whole list (so X always swaps to "the next
        # location"), regardless of which mode you're in.
        self.locations: list[tuple] = [("Here", None, None)] + list(KNOWN_METROS)
        self.loc_idx = 0
        self.location = ("Here", 0.0, 0.0)
        self.gps_acc = 0.0
        self.results: list[dict] = []
        self.visible: list[dict] = []
        self.flock_only = True
        self.status = "init"               # init | no_gps | querying | ready | error
        self.error = ""
        self._t0 = time.time()
        top = statusbar.HEIGHT + 58
        bot = config.SCREEN_H - 28
        self.list = ListView(pygame.Rect(10, top, config.SCREEN_W - 20, bot - top), row_h=42)
        self._set_location()

    def _set_location(self):
        """Resolve self.locations[self.loc_idx] to a usable (name, lat, lon).
        For the 'Here' entry, hit /api/gps; if not connected, sit in no_gps."""
        entry = self.locations[self.loc_idx]
        if entry[0] == "Here":
            gps = _read_phone_gps()
            if gps is None:
                self.location = ("Here", 0.0, 0.0)
                self.gps_acc = 0.0
                self.status = "no_gps"
                self.results = []; self.visible = []; self.list.set_items([])
                return
            self.location = ("Here", gps[0], gps[1])
            self.gps_acc = gps[2]
        else:
            self.location = entry
            self.gps_acc = 0.0
        self._query()

    def _apply_filter(self):
        if self.flock_only:
            self.visible = [d for d in self.results
                            if "flock" in (d.get("operator") or "").lower()]
        else:
            self.visible = list(self.results)
        self.list.set_items(self.visible)

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
            self._apply_filter()
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
            self.loc_idx = (self.loc_idx + 1) % len(self.locations)
            self._set_location()
            return
        if action == "Y":          # re-poll GPS / re-query the same location
            self._set_location()
            return
        if action in ("L", "R"):              # toggle Flock-only vs all ALPRs
            self.flock_only = not self.flock_only
            self._apply_filter()
            return
        r = self.list.on_action(action)
        if r == "back" or action in ("EXIT", "MENU"):
            self.app.pop()
        elif r == "select" and self.list.selected():
            from .flock_detail import FlockDetailScreen
            self.app.push(FlockDetailScreen(self.app, self.list.selected(), self.location))

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
        is_here = self.location[0] == "Here"
        head_label = "@ Here (live GPS)" if is_here else f"@ {self.location[0]}"
        head = ui.render(head_label, True, accent)
        surf.blit(head, (12, y))
        if self.status == "no_gps":
            sub = small.render("phone-GPS link not connected · X for a city", True, dim)
        else:
            extra = f"  ±{self.gps_acc:.0f}m" if (is_here and self.gps_acc) else ""
            sub = small.render(
                f"{self.location[1]:.4f}, {self.location[2]:.4f}{extra}   ·  20 km radius   ·  OSM",
                True, dim)
        surf.blit(sub, (12, y + 22))
        pygame.draw.line(surf, accent, (12, y + 42), (config.SCREEN_W - 12, y + 42), 1)

        if self.status == "no_gps":
            t = ui.render("Phone GPS not connected.", True, dim)
            surf.blit(t, t.get_rect(center=(cx, config.SCREEN_H // 2 - 24)))
            t2 = small.render("On your phone, open the NeoBoX Mobile Link", True, dim)
            t3 = small.render("(Settings -> Web UI) and allow Location.", True, dim)
            surf.blit(t2, t2.get_rect(center=(cx, config.SCREEN_H // 2 + 4)))
            surf.blit(t3, t3.get_rect(center=(cx, config.SCREEN_H // 2 + 22)))
            t4 = small.render("Press Y once connected, or X for a city.", True, accent)
            surf.blit(t4, t4.get_rect(center=(cx, config.SCREEN_H // 2 + 50)))
            return
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
        if not self.visible:
            t = small.render("No confirmed-Flock cameras in this area.", True, dim)
            surf.blit(t, t.get_rect(center=(cx, config.SCREEN_H // 2 - 12)))
            t2 = small.render("Press LR to show all OSM-tagged ALPRs.", True, dim)
            surf.blit(t2, t2.get_rect(center=(cx, config.SCREEN_H // 2 + 10)))
            return

        # filter + counts chip: "12 FLOCK · 80 ALPR"
        n_flock = sum(1 for d in self.results
                      if "flock" in (d.get("operator") or "").lower())
        n_total = len(self.results)
        mode = "FLOCK" if self.flock_only else "ALL ALPR"
        cnt_text = f"{mode}: {len(self.visible)}   ·   {n_flock} flock / {n_total} alpr"
        cnt = small.render(cnt_text, True, accent)
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
        if self.status == "no_gps":
            return [("Y", "retry GPS"), ("X", "use a city"), ("B", "back")]
        loc_label = "next loc" if self.location[0] == "Here" else "next city"
        return [("A", "details"), ("LR", "filter"), ("X", loc_label), ("Y", "refresh"), ("B", "back")]
