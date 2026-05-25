"""WiFi manager screen: scan, pick, enter password, connect (via nmcli)."""
from __future__ import annotations

import threading
import time

import pygame

from . import Screen
from .. import config, wifi
from ..ui import statusbar
from .textinput import OnScreenKeyboard

_SPIN = "|/-\\"
ROW_H = 30


class WifiScreen(Screen):
    modal = True   # handle MENU/EXIT here (don't pop to overlays mid-flow)

    def __init__(self, app):
        super().__init__(app)
        self.title = "WIFI"
        self.nets: list[dict] = []
        self.index = 0
        self.scroll = 0
        self.state = "scanning"     # scanning | list | connecting
        self.msg = ""
        self.busy_ssid = ""
        self._lock = threading.Lock()
        if not wifi.available():
            self.state = "list"
            self.msg = "nmcli not available"
        else:
            self._start_scan("auto")

    # --- background work ------------------------------------------------
    def _start_scan(self, rescan="auto"):
        self.state = "scanning"
        threading.Thread(target=self._scan_thread, args=(rescan,), daemon=True).start()

    def _scan_thread(self, rescan):
        nets = wifi.scan(rescan=rescan)
        with self._lock:
            self.nets = nets
            self.index = min(self.index, max(0, len(nets) - 1))
            self.state = "list"

    def _connect(self, ssid, password):
        self.state = "connecting"
        self.busy_ssid = ssid
        threading.Thread(target=self._connect_thread, args=(ssid, password), daemon=True).start()

    def _connect_thread(self, ssid, password):
        ok, msg = wifi.connect(ssid, password)
        nets = wifi.scan("no")
        with self._lock:
            self.msg = (f"Connected: {ssid}" if ok else f"Failed: {msg}")[:46]
            self.nets = nets
            self.state = "list"

    # --- input ----------------------------------------------------------
    def on_action(self, action: str):
        if self.state == "connecting":
            return
        if self.state == "scanning":
            if action in ("B", "EXIT", "MENU"):
                self.app.pop()
            return
        # list state
        if action == "UP" and self.nets:
            self.index = (self.index - 1) % len(self.nets)
        elif action == "DOWN" and self.nets:
            self.index = (self.index + 1) % len(self.nets)
        elif action == "X":
            self._start_scan("yes")
        elif action == "Y":
            self.msg = "Disconnecting…"
            threading.Thread(target=self._disconnect_thread, daemon=True).start()
        elif action in ("B", "MENU", "EXIT"):
            self.app.pop()
        elif action == "A" and self.nets:
            self._select(self.nets[self.index])

    def _disconnect_thread(self):
        s = wifi.disconnect()
        nets = wifi.scan("no")
        with self._lock:
            self.msg = f"Disconnected: {s}" if s else "Not connected"
            self.nets = nets

    def _select(self, net):
        if net["in_use"]:
            self.msg = f"Already on {net['ssid']}"
            return
        if net["secured"]:
            self.app.push(OnScreenKeyboard(
                self.app, f"Password: {net['ssid'][:18]}",
                lambda pw: self._on_password(net, pw)))
        else:
            self._connect(net["ssid"], None)

    def _on_password(self, net, pw):
        self.app.pop()          # close the keyboard
        self._connect(net["ssid"], pw)

    # --- draw -----------------------------------------------------------
    def update(self, dt):
        pass

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, self.title)
        font = theme.font("ui")
        small = theme.font("small")

        if self.state == "scanning":
            spin = _SPIN[int(time.time() * 8) % 4]
            t = font.render(f"{spin}  scanning…", True, theme.color("text"))
            surf.blit(t, t.get_rect(center=(config.SCREEN_W // 2, config.SCREEN_H // 2)))
            return

        if self.state == "connecting":
            spin = _SPIN[int(time.time() * 8) % 4]
            t = font.render(f"{spin}  connecting to", True, theme.color("text"))
            surf.blit(t, t.get_rect(center=(config.SCREEN_W // 2, config.SCREEN_H // 2 - 12)))
            s = font.render(self.busy_ssid[:24], True, theme.color("accent"))
            surf.blit(s, s.get_rect(center=(config.SCREEN_W // 2, config.SCREEN_H // 2 + 12)))
            return

        # list
        top = statusbar.HEIGHT + 4
        bottom = config.SCREEN_H - 24
        rows = max(1, (bottom - top - 16) // ROW_H)
        with self._lock:
            nets = list(self.nets)
        if not nets:
            t = small.render("No networks found. Press X to rescan.", True, theme.color("text_dim"))
            surf.blit(t, t.get_rect(center=(config.SCREEN_W // 2, config.SCREEN_H // 2)))
        else:
            if self.index < self.scroll:
                self.scroll = self.index
            elif self.index >= self.scroll + rows:
                self.scroll = self.index - rows + 1
            for vi in range(rows):
                i = self.scroll + vi
                if i >= len(nets):
                    break
                self._draw_row(surf, theme, font, small, nets[i], top + vi * ROW_H,
                               selected=(i == self.index))
        # status line
        if self.msg:
            m = small.render(self.msg, True, theme.color("text_dim"))
            surf.blit(m, (10, bottom - 2))

    def _draw_row(self, surf, theme, font, small, net, y, selected):
        rect = pygame.Rect(8, y, config.SCREEN_W - 16, ROW_H - 4)
        if selected:
            pygame.draw.rect(surf, theme.color("tile_sel"), rect, border_radius=6)
            pygame.draw.rect(surf, theme.color("accent"), rect, width=1, border_radius=6)
        # signal bars (left)
        self._bars(surf, theme, rect.x + 8, rect.centery, net["signal"])
        # ssid
        name = net["ssid"]
        col = theme.color("accent") if net["in_use"] else theme.color("text")
        label = font.render(name[:24], True, col)
        surf.blit(label, (rect.x + 40, rect.centery - label.get_height() // 2))
        # lock + connected marker (right)
        rx = rect.right - 10
        if net["in_use"]:
            c = small.render("✓ connected", True, theme.color("accent"))
            surf.blit(c, (rx - c.get_width(), rect.centery - c.get_height() // 2))
            rx -= c.get_width() + 8
        if net["secured"]:
            lock = small.render("🔒", True, theme.color("text_dim"))
            if lock.get_width() < 4:   # font lacks emoji -> ascii
                lock = small.render("[*]", True, theme.color("text_dim"))
            surf.blit(lock, (rx - lock.get_width(), rect.centery - lock.get_height() // 2))

    def _bars(self, surf, theme, x, cy, signal):
        n = 4
        on = max(1, round(signal / 25))
        for i in range(n):
            h = 4 + i * 4
            c = theme.color("accent") if i < on else theme.color("text_dim")
            pygame.draw.rect(surf, c, (x + i * 6, cy + 8 - h, 4, h))

    def hints(self):
        if self.state == "list":
            return [("A", "connect"), ("X", "rescan"), ("Y", "disconnect"), ("B", "back")]
        return [("B", "back")]
