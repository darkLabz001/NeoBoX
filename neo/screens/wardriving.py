"""Wardriving Dashboard screen — WiGLE logging + Mobile GPS + BT/WiFi adapters."""
from __future__ import annotations

import os
import subprocess
import threading
import time
import re
import socket
import io
import csv
from pathlib import Path
from datetime import datetime

import pygame
import qrcode

from . import Screen
from .. import config

class WardrivingScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.title = "WARDRIVING"
        self.aps_found = 0
        self.bt_found = 0
        self.handshakes = 0
        self.gps = {"lat": 0.0, "lon": 0.0, "alt": 0.0, "acc": 0.0}
        self.linked = False
        self._seen_macs = set()
        self._seen_bt = set()
        
        # QR Code for phone link (HTTPS)
        self.qr_surf = self._generate_qr()
        
        # WiGLE CSV Log
        self.log_path = Path.home() / "neo" / "loot" / "wardrive" / time.strftime("wardrive-%Y%m%d-%H%M%S.csv")
        self._init_log()
        
        self._stop_event = threading.Event()
        self._wifi_thread = None
        self._bt_thread = None
        self._gps_thread = None
        
        self._start_threads()

    def _init_log(self):
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "w", newline="") as f:
                f.write("WigleWifi-1.4,appRelease=NeoBoX-2.0,model=Handheld,release=0.1,device=NeoBoX,display=None,board=None,brand=Neo\n")
                f.write("MAC,SSID,AuthMode,FirstSeen,Channel,RSSI,CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,Type\n")
        except: pass

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except: return "127.0.0.1"

    def _generate_qr(self):
        ip = self._get_local_ip()
        url = f"https://{ip}:8888/mobile"
        qr = qrcode.QRCode(version=1, box_size=3, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="white", back_color="black").convert("RGB")
        data = img.tobytes()
        return pygame.image.fromstring(data, img.size, "RGB")

    def _start_threads(self):
        self._stop_event.clear()
        self._wifi_thread = threading.Thread(target=self._wifi_loop, daemon=True)
        self._wifi_thread.start()
        self._bt_thread = threading.Thread(target=self._bt_loop, daemon=True)
        self._bt_thread.start()
        self._gps_thread = threading.Thread(target=self._gps_poll_loop, daemon=True)
        self._gps_thread.start()

    def _wifi_loop(self):
        iface = "wlan1"
        while not self._stop_event.is_set():
            try:
                # Terse output uses ':' as separator, but MACs also have ':'. 
                # nmcli escapes them as \:
                cmd = ["sudo", "nmcli", "-t", "-f", "BSSID,SSID,SIGNAL,SECURITY,CHAN", "dev", "wifi", "list", "ifname", iface]
                out = subprocess.check_output(cmd, text=True).splitlines()
                for line in out:
                    if not line.strip(): continue
                    # Replace escaped colons with | temporarily
                    tmp = line.replace("\\:", "|")
                    parts = tmp.split(":")
                    if len(parts) >= 5:
                        bssid = parts[0].replace("|", ":")
                        ssid = parts[1].replace("|", ":")
                        rssi = parts[2]
                        security = parts[3]
                        chan = parts[4]
                        if bssid not in self._seen_macs:
                            self._seen_macs.add(bssid)
                            self.aps_found += 1
                            if self.linked:
                                self._log_to_wigle(bssid, ssid, security, chan, rssi, "WIFI")
            except: pass
            time.sleep(5)

    def _bt_loop(self):
        iface = "hci1"
        while not self._stop_event.is_set():
            try:
                cmd = ["sudo", "hcitool", "-i", iface, "scan", "--flush"]
                out = subprocess.check_output(cmd, text=True).splitlines()
                for line in out:
                    m = re.search(r"([0-9A-F:]{17})\s+(.*)", line)
                    if m:
                        mac, name = m.group(1), m.group(2)
                        if mac not in self._seen_bt:
                            self._seen_bt.add(mac)
                            self.bt_found += 1
                            if self.linked:
                                self._log_to_wigle(mac, name, "[BT]", 0, -70, "BT")
                # Briefly ping lescan to wake up cache
                subprocess.run(["sudo", "timeout", "-s", "INT", "1s", "hcitool", "-i", iface, "lescan"], capture_output=True)
            except: pass
            time.sleep(3)

    def _log_to_wigle(self, mac, ssid, auth, chan, rssi, type_str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.log_path, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([mac, ssid, auth, ts, chan, rssi, self.gps['lat'], self.gps['lon'], self.gps['alt'], self.gps['acc'], type_str])
        except: pass

    def _gps_poll_loop(self):
        import requests
        while not self._stop_event.is_set():
            try:
                r = requests.get("https://127.0.0.1:8888/api/gps", timeout=1, verify=False)
                data = r.json()
                if time.time() - data.get('last_seen', 0) < 20:
                    self.gps = data.get('gps', self.gps)
                    self.linked = True
                else:
                    self.linked = False
            except: pass
            time.sleep(1)

    def on_action(self, action: str):
        if action == "B":
            self._stop_event.set()
            self.app.pop()

    def update(self, dt: float):
        pass

    def is_animating(self):
        return True

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "RECON: WARDRIVING")

        accent = theme.color("accent")
        dim = theme.color("text_dim")
        ui, small = theme.font("ui"), theme.font("small")
        
        link_rect = pygame.Rect(10, 40, 180, 110)
        pygame.draw.rect(surf, theme.color("tile"), link_rect, border_radius=8)
        pygame.draw.rect(surf, accent if self.linked else dim, link_rect, width=1, border_radius=8)
        
        if not self.linked:
            if hasattr(self, 'qr_surf'):
                surf.blit(self.qr_surf, (link_rect.x + 10, link_rect.y + 10))
            surf.blit(small.render("SCAN (HTTPS)", True, accent), (link_rect.x + 85, link_rect.y + 35))
            surf.blit(small.render("FOR GPS PERMS", True, accent), (link_rect.x + 85, link_rect.y + 50))
        else:
            surf.blit(small.render("PHONE LINK: ACTIVE", True, theme.color("danger")), (link_rect.x + 10, link_rect.y + 10))
            surf.blit(ui.render(f"LAT: {self.gps['lat']:.4f}", True, theme.color("text")), (link_rect.x + 10, link_rect.y + 35))
            surf.blit(ui.render(f"LON: {self.gps['lon']:.4f}", True, theme.color("text")), (link_rect.x + 10, link_rect.y + 60))
            surf.blit(small.render(f"ACCURACY: {self.gps['acc']:.1f}m", True, dim), (link_rect.x + 10, link_rect.y + 85))

        stats_rect = pygame.Rect(200, 40, config.SCREEN_W - 210, 110)
        pygame.draw.rect(surf, theme.color("tile"), stats_rect, border_radius=8)
        pygame.draw.rect(surf, accent, stats_rect, width=1, border_radius=8)
        
        surf.blit(small.render("WIFI APS", True, dim), (stats_rect.x + 10, stats_rect.y + 10))
        surf.blit(theme.font("title").render(str(self.aps_found), True, accent), (stats_rect.x + 10, stats_rect.y + 25))
        
        surf.blit(small.render("BT DEVICES", True, dim), (stats_rect.x + 10, stats_rect.y + 60))
        surf.blit(theme.font("title").render(str(self.bt_found), True, theme.color("accent2")), (stats_rect.x + 10, stats_rect.y + 75))

        log_rect = pygame.Rect(10, 160, config.SCREEN_W - 20, config.SCREEN_H - 195)
        pygame.draw.rect(surf, (0, 0, 0, 100), log_rect, border_radius=8)
        pygame.draw.rect(surf, accent, log_rect, width=1, border_radius=8)
        
        surf.blit(small.render("DUAL-ADAPTER LOGGING", True, dim), (log_rect.x + 10, log_rect.y + 5))
        surf.blit(small.render(f"> WiFi: wlan1 (Alfa) | BT: hci1 (USB)", True, theme.color("text")), (log_rect.x + 10, log_rect.y + 25))
        total = len(self._seen_macs) + len(self._seen_bt)
        surf.blit(small.render(f"> Total WiGLE Entries: {total}", True, theme.color("text")), (log_rect.x + 10, log_rect.y + 42))

    def hints(self):
        return [("B", "stop & back")]
