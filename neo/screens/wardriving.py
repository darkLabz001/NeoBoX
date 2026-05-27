"""Wardriving PRO 2.0 — Handshake Verification + OUI Lookup + Tactical Audio."""
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
from collections import deque

import pygame
import qrcode

from . import Screen
from .. import config

class WardrivingScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.title = "WARDRIVING PRO 2.0"
        self.aps_found = 0
        self.bt_found = 0
        self.handshakes = 0
        self.verified_hashes = 0
        self.gps = {"lat": 0.0, "lon": 0.0, "alt": 0.0, "acc": 0.0}
        self.linked = False
        
        self._seen_macs = set()
        self._seen_bt = set()
        self.log_buffer = deque(maxlen=8)
        
        # Adapters
        self.wifi_iface = "wlan1"
        self.bt_iface = "hci1"
        
        # QR Code for phone link
        self.qr_surf = self._generate_qr()
        
        # Paths
        self.loot_dir = Path.home() / "neo" / "loot" / "wardrive"
        self.log_path = self.loot_dir / time.strftime("wardrive-%Y%m%d-%H%M%S.csv")
        self.pcap_path = self.loot_dir / time.strftime("capture-%Y%m%d-%H%M%S.pcapng")
        self._init_log()
        
        self._stop_event = threading.Event()
        self._procs = []
        
        # Vendor OUI Cache (Simple lookup)
        self.oui_db = self._load_oui_lite()
        
        self._start_engines()

    def _load_oui_lite(self):
        # A tiny embedded DB for common manufacturers
        return {
            "00:03:93": "Apple", "00:05:02": "Apple", "00:0A:95": "Apple",
            "00:14:22": "Dell", "00:16:3E": "Xen", "00:1A:11": "Google",
            "00:24:D7": "Intel", "34:E1:2D": "Lenovo", "B8:27:EB": "RaspberryPi",
            "DC:A6:32": "RaspberryPi", "E4:5F:01": "RaspberryPi",
            "00:C0:CA": "Alfa", "00:25:9C": "Cisco", "00:1D:AA": "TP-Link",
            "B0:4E:26": "TP-Link", "C0:25:E9": "Microsoft", "D8:3B:BF": "Samsung"
        }

    def _get_vendor(self, mac: str) -> str:
        prefix = mac.upper()[:8]
        return self.oui_db.get(prefix, "Unknown")

    def _init_log(self):
        try:
            self.loot_dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "w", newline="") as f:
                f.write("WigleWifi-1.4,appRelease=NeoBoX-PRO-2,model=Handheld,release=0.1,device=NeoBoX,display=None,board=None,brand=Neo\n")
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
        url = f"http://{ip}:8888/mobile"
        qr = qrcode.QRCode(version=1, box_size=3, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="white", back_color="black").convert("RGB")
        return pygame.image.fromstring(img.tobytes(), img.size, "RGB")

    def _start_engines(self):
        self._stop_event.clear()
        threading.Thread(target=self._wifi_engine, daemon=True).start()
        threading.Thread(target=self._bt_engine, daemon=True).start()
        threading.Thread(target=self._gps_poll_loop, daemon=True).start()
        threading.Thread(target=self._verification_loop, daemon=True).start()

    def _wifi_engine(self):
        # Prepare interface
        subprocess.run(["sudo", "ip", "link", "set", self.wifi_iface, "down"], capture_output=True)
        subprocess.run(["sudo", "iw", "dev", self.wifi_iface, "set", "type", "monitor"], capture_output=True)
        subprocess.run(["sudo", "ip", "link", "set", self.wifi_iface, "up"], capture_output=True)
        
        self.log_buffer.append(f"[*] wlan1: Monitor Mode active")

        # Start hcxdumptool
        cmd = [
            "sudo", "hcxdumptool", "-i", self.wifi_iface,
            "-o", str(self.pcap_path),
            "--enable_status=1"
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self._procs.append(proc)
            
            while not self._stop_event.is_set():
                try:
                    # Scan for WiGLE details using wlan0 (internal)
                    scan_cmd = ["sudo", "nmcli", "-t", "-f", "BSSID,SSID,SIGNAL,SECURITY,CHAN", "dev", "wifi", "list", "ifname", "wlan0"]
                    out = subprocess.check_output(scan_cmd, text=True).splitlines()
                    for line in out:
                        tmp = line.replace("\\:", "|")
                        parts = tmp.split(":")
                        if len(parts) >= 5:
                            bssid = parts[0].replace("|", ":")
                            ssid = parts[1].replace("|", ":")
                            if bssid not in self._seen_macs:
                                self._seen_macs.add(bssid)
                                self.aps_found += 1
                                self._log_to_wigle(bssid, ssid, parts[3], parts[4], parts[2], "WIFI")
                                vendor = self._get_vendor(bssid)
                                self.log_buffer.append(f"[+] WiFi: {ssid[:12]} ({vendor})")
                                self.app.sfx.play("move") # Low-pitch ping
                except: pass
                time.sleep(4)
        except Exception as e:
            self.log_buffer.append(f"[!] WiFi Error: {str(e)[:20]}")

    def _verification_loop(self):
        """Periodically run hcxpcapngtool to verify valid hashes in the pcap."""
        while not self._stop_event.is_set():
            if self.pcap_path.exists() and self.pcap_path.stat().st_size > 1024:
                try:
                    # -v 1 gives a summary of PMKIDs and EAPOL handshakes
                    cmd = ["hcxpcapngtool", str(self.pcap_path)]
                    out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
                    
                    # Look for totals in the summary
                    pmkids = re.search(r"written to PMKID file.*?(\d+)", out)
                    eapols = re.search(r"written to 22000 file.*?(\d+)", out)
                    
                    new_total = 0
                    if pmkids: new_total += int(pmkids.group(1))
                    if eapols: new_total += int(eapols.group(1))
                    
                    if new_total > self.verified_hashes:
                        diff = new_total - self.verified_hashes
                        self.log_buffer.append(f"[*] ALERT: {diff} NEW HASHES VERIFIED!")
                        self.app.sfx.play("select") # High-pitch alert
                        self.verified_hashes = new_total
                except: pass
            time.sleep(10)

    def _bt_engine(self):
        while not self._stop_event.is_set():
            try:
                cmd = ["sudo", "hcitool", "-i", self.bt_iface, "scan", "--flush"]
                out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).splitlines()
                for line in out:
                    m = re.search(r"([0-9A-F:]{17})\s+(.*)", line)
                    if m:
                        mac, name = m.group(1), m.group(2)
                        if mac not in self._seen_bt:
                            self._seen_bt.add(mac)
                            self.bt_found += 1
                            if self.linked:
                                self._log_to_wigle(mac, name, "[BT]", 0, -70, "BT")
                            self.log_buffer.append(f"[+] BT: {name[:12]} ({self._get_vendor(mac)})")
                subprocess.run(["sudo", "timeout", "-s", "INT", "1s", "hcitool", "-i", self.bt_iface, "lescan"], capture_output=True)
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
                r = requests.get("http://127.0.0.1:8888/api/gps", timeout=1)
                data = r.json()
                if time.time() - data.get('last_seen', 0) < 20:
                    self.gps = data.get('gps', self.gps)
                    self.linked = True
                else:
                    self.linked = False
            except: pass
            time.sleep(1)

    def _stop_all(self):
        self._stop_event.set()
        for p in self._procs:
            try: p.terminate()
            except: pass
        subprocess.run(["sudo", "pkill", "-f", "hcxdumptool"], capture_output=True)

    def on_action(self, action: str):
        if action == "B":
            self._stop_all()
            self.app.pop()

    def update(self, dt: float):
        pass

    def is_animating(self):
        return True

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "RECON: WARDRIVING PRO 2.0")

        accent = theme.color("accent")
        accent2 = theme.color("accent2")
        dim = theme.color("text_dim")
        ui, small = theme.font("ui"), theme.font("small")
        title_f = theme.font("title")
        
        # 1. GPS LINK (Left)
        link_rect = pygame.Rect(10, 40, 160, 110)
        pygame.draw.rect(surf, theme.color("tile"), link_rect, border_radius=8)
        pygame.draw.rect(surf, accent if self.linked else dim, link_rect, width=1, border_radius=8)
        
        if not self.linked:
            if hasattr(self, 'qr_surf'):
                surf.blit(self.qr_surf, (link_rect.centerx - self.qr_surf.get_width()//2, link_rect.y + 5))
            surf.blit(small.render("SCAN TO LINK GPS", True, accent), (link_rect.x + 25, link_rect.bottom - 18))
        else:
            surf.blit(small.render("PHONE GPS: ACTIVE", True, theme.color("danger")), (link_rect.x + 10, link_rect.y + 8))
            surf.blit(ui.render(f"LAT: {self.gps['lat']:.5f}", True, theme.color("text")), (link_rect.x + 10, link_rect.y + 30))
            surf.blit(ui.render(f"LON: {self.gps['lon']:.5f}", True, theme.color("text")), (link_rect.x + 10, link_rect.y + 52))
            # Accuracy Bar
            pygame.draw.rect(surf, (0,0,0), (link_rect.x + 10, link_rect.y + 85, 140, 4))
            acc_w = max(2, 140 - int(self.gps['acc'] * 2))
            pygame.draw.rect(surf, accent, (link_rect.x + 10, link_rect.y + 85, min(140, acc_w), 4))
            surf.blit(small.render(f"ACCURACY: {self.gps['acc']:.1f}m", True, dim), (link_rect.x + 10, link_rect.y + 92))

        # 2. STATS (Right)
        stats_rect = pygame.Rect(180, 40, config.SCREEN_W - 190, 110)
        pygame.draw.rect(surf, theme.color("tile"), stats_rect, border_radius=8)
        pygame.draw.rect(surf, accent, stats_rect, width=1, border_radius=8)
        
        surf.blit(small.render("WIFI APS", True, dim), (stats_rect.x + 10, stats_rect.y + 5))
        surf.blit(title_f.render(str(self.aps_found), True, accent), (stats_rect.x + 10, stats_rect.y + 18))
        
        surf.blit(small.render("BT DEVICES", True, dim), (stats_rect.x + 110, stats_rect.y + 5))
        surf.blit(title_f.render(str(self.bt_found), True, accent2), (stats_rect.x + 110, stats_rect.y + 18))

        surf.blit(small.render("VERIFIED HASHES", True, dim), (stats_rect.x + 10, stats_rect.y + 60))
        h_color = theme.color("danger") if self.verified_hashes > 0 else dim
        surf.blit(title_f.render(str(self.verified_hashes), True, h_color), (stats_rect.x + 10, stats_rect.y + 75))

        # 3. LIVE LOG (Bottom)
        log_rect = pygame.Rect(10, 160, config.SCREEN_W - 20, config.SCREEN_H - 195)
        pygame.draw.rect(surf, (0, 0, 0, 180), log_rect, border_radius=8)
        pygame.draw.rect(surf, accent, log_rect, width=1, border_radius=8)
        
        y = log_rect.y + 5
        for entry in self.log_buffer:
            col = theme.color("text")
            if "[+]" in entry: col = accent
            if "[*]" in entry: col = theme.color("danger")
            surf.blit(small.render(entry, True, col), (log_rect.x + 10, y))
            y += 14
        
        # Interface Indicators
        if int(time.time()) % 2 == 0:
            pygame.draw.circle(surf, accent, (config.SCREEN_W - 25, 55), 4) # WiFi pulse
            pygame.draw.circle(surf, accent2, (config.SCREEN_W - 40, 55), 4) # BT pulse

    def hints(self):
        return [("B", "stop & exit")]
