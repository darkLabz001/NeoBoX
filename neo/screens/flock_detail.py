"""Detail view for a single Flock / ALPR camera.

Shows everything OSM has on it (operator, name, direction, type), distance
from the query origin, copy-able coordinates, a Google Maps URL for street
view / navigation, and an OSM map tile of the location with a crosshair.

Honest in the UI: Flock streams privately to law enforcement and property
owners; the live feed is not publicly viewable. This screen helps you find
and identify the camera physically, not access it."""
from __future__ import annotations

import io
import math
import threading
import urllib.request

import pygame

from . import Screen
from .. import config
from ..ui import statusbar


def _tile_xy(lat: float, lon: float, z: int) -> tuple[int, int]:
    n = 2.0 ** z
    x = int((lon + 180.0) / 360.0 * n)
    rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(rad) + 1 / math.cos(rad)) / math.pi) / 2.0 * n)
    return x, y


def _dist_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class FlockDetailScreen(Screen):
    modal = True

    def __init__(self, app, item: dict, origin: tuple[str, float, float]):
        super().__init__(app)
        self.item = item
        self.origin = origin       # (name, lat, lon)
        self.title = "CAMERA"
        self.tile: pygame.Surface | None = None
        self._tile_err = False
        threading.Thread(target=self._fetch_tile, daemon=True).start()

    def _fetch_tile(self):
        try:
            x, y = _tile_xy(self.item["lat"], self.item["lon"], 17)
            # Disk cache so repeated opens are instant and we respect OSM
            # tile-usage policy ("Heavy use will be blocked / cache aggressively").
            cache_dir = config.CACHE_DIR / "osm_tiles"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache = cache_dir / f"17_{x}_{y}.png"
            if cache.exists() and cache.stat().st_size > 0:
                data = cache.read_bytes()
            else:
                url = f"https://tile.openstreetmap.org/17/{x}/{y}.png"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "NeoBoX/0.1 (+https://github.com/darkLabz001/NeoBoX)",
                })
                data = urllib.request.urlopen(req, timeout=10).read()
                cache.write_bytes(data)
            img = pygame.image.load(io.BytesIO(data))
            # OSM tiles come back as 8-bit indexed PNGs; pygame.smoothscale
            # only accepts 24/32-bit surfaces, so promote first.
            if img.get_bitsize() < 24:
                promoted = pygame.Surface(img.get_size())
                promoted.blit(img, (0, 0))
                img = promoted
            self.tile = pygame.transform.smoothscale(img, (190, 190))
        except Exception as exc:
            print(f"[flock] tile fetch failed: {exc}")
            self._tile_err = True

    def on_action(self, action: str):
        if action in ("B", "EXIT", "MENU"):
            self.app.pop()

    def is_animating(self):
        return self.tile is None and not self._tile_err

    def draw(self, surf, theme):
        surf.fill(theme.color("bg"))
        self.app.statusbar.draw(surf, theme, self.title)
        ui = theme.font("ui")
        small = theme.font("small")
        accent = theme.color("accent")
        text = theme.color("text")
        dim = theme.color("text_dim")
        warn = theme.color("warn")

        op = (self.item.get("operator") or "").strip()
        nm = (self.item.get("name") or "").strip()
        is_flock = "flock" in op.lower()
        # operator title (color flock vs other)
        y = statusbar.HEIGHT + 12
        title_col = accent if is_flock else warn
        surf.blit(ui.render(op or "UNKNOWN OPERATOR", True, title_col), (14, y))
        y += 26
        if nm:
            surf.blit(small.render(nm[:42], True, text), (14, y))
            y += 18
        else:
            surf.blit(small.render("(no name tag)", True, dim), (14, y))
            y += 18

        # distance + coords
        dist = _dist_m(self.origin[1], self.origin[2], self.item["lat"], self.item["lon"])
        dstr = f"{dist / 1000:.2f} km" if dist >= 1000 else f"{int(dist)} m"
        surf.blit(small.render(f"{dstr} from {self.origin[0]}", True, dim), (14, y))
        y += 16
        surf.blit(small.render(f"{self.item['lat']:.6f},  {self.item['lon']:.6f}",
                               True, accent), (14, y))
        y += 22

        # OSM tags worth showing
        for label, key in (("type", "type"), ("direction", "direction"),
                           ("osm", "_osm_link")):
            if key == "_osm_link":
                v = f"{self.item.get('osm_type','')}/{self.item.get('osm_id','')}"
            else:
                v = self.item.get(key, "")
            if v:
                surf.blit(small.render(f"{label}:  {v}", True, dim), (14, y))
                y += 15

        # Google Maps URL — readable enough to type on a phone for Street View
        y += 6
        surf.blit(small.render("Open on a phone (Street View / drive to):", True, dim), (14, y))
        y += 15
        gmaps = f"maps.google.com/?q={self.item['lat']:.5f},{self.item['lon']:.5f}"
        surf.blit(small.render(gmaps, True, accent), (14, y))
        y += 24

        # honest note about the feed
        surf.blit(small.render("Live feed: NOT PUBLIC", True, warn), (14, y))
        y += 14
        surf.blit(small.render("Flock streams privately to law enforcement;",
                               True, warn), (14, y))
        y += 14
        surf.blit(small.render("publicly viewable feeds are in CCTV Viewer.",
                               True, warn), (14, y))

        # right column: map tile with crosshair
        tx, ty, ts = config.SCREEN_W - 204, statusbar.HEIGHT + 14, 190
        if self.tile is not None:
            surf.blit(self.tile, (tx, ty))
            cx, cy = tx + ts // 2, ty + ts // 2
            pygame.draw.circle(surf, accent, (cx, cy), 8, 2)
            pygame.draw.line(surf, accent, (cx - 14, cy), (cx + 14, cy), 1)
            pygame.draw.line(surf, accent, (cx, cy - 14), (cx, cy + 14), 1)
        else:
            box = pygame.Rect(tx, ty, ts, ts)
            pygame.draw.rect(surf, theme.color("tile"), box, border_radius=8)
            msg = small.render("loading map…" if not self._tile_err else "(map unavailable)",
                               True, dim)
            surf.blit(msg, msg.get_rect(center=box.center))
        pygame.draw.rect(surf, accent, (tx, ty, ts, ts), width=1, border_radius=8)
        # caption under the tile: zoom level + coords
        surf.blit(small.render("OSM z17 · crosshair = cam", True, dim),
                  (tx + 4, ty + ts + 4))

    def hints(self):
        return [("B", "back")]
