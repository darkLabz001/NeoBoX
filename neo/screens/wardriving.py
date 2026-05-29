"""Wardriving PRO 3.5 — High-perf discovery + Signal Density Graph."""
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
from ..font_cache import render_text

class WardrivingScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.title = "WARDRIVING PRO 3.5"
        self.aps_found = 0
        self.bt_found = 0
        self.verified_hashes = 0
        self.gps = {"lat": 0.0, "lon": 0.0, "alt": 0.0, "acc": 0.0}
        self.linked = False
        
        self._seen_macs = set()
        self._seen_bt = set()
        self.log_buffer = deque(maxlen=8)
        
        # Performance: Signal Density Graph
        self.signal_history = deque([0] * 60, maxlen=60) # 60 seconds of history
        self._last_graph_update = 0
        
        # Adapters: pick the monitor-capable wifi iface at runtime instead of
        # hard-coding wlan1. The Pi assigns wlanN by boot order, and the Pi's
        # onboard radio (which only supports IBSS+managed) sometimes wins the
        # "wlan1" slot, leaving the Alfa as wlan0.
        self.wifi_iface = self._pick_monitor_iface()
        self.bt_iface = "hci1"
        
        # QR Code for phone link
        self.qr_surf = self._generate_qr()
        
        # Paths
        self.loot_dir = Path.home() / "neo" / "loot" / "wardrive"
        self.log_path = self.loot_dir / time.strftime("wardrive-%Y%m%d-%H%M%S.csv")
        self.pcap_path = self.loot_dir / time.strftime("capture-%Y%m%d-%H%M%S.pcapng")
        self._init_log()
        
        self._stop_event = threading.Event()
        self._wifi_proc = None
        
        # Simple OUI DB
        self.oui_db = self._load_oui_lite()
        
        self._start_engines()

    def _load_oui_lite(self):
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

    def _iface_is_default_route(self, iface: str) -> bool:
        """True if `iface` is currently carrying the default route — i.e.
        flipping it to monitor will sever the device's internet/SSH."""
        try:
            out = subprocess.check_output(
                ["ip", "route", "show", "default"],
                text=True, stderr=subprocess.DEVNULL)
            return f" dev {iface} " in (" " + out + " ")
        except Exception:
            return False

    def _pick_monitor_iface(self) -> str | None:
        """Find a wlan iface whose phy actually supports monitor mode.
        Returns the iface name (e.g. 'wlan0') or None if no adapter qualifies.
        Querying `iw phy <phy> info` and looking for 'monitor' in the
        Supported interface modes block is the only reliable test — the OS
        does not expose this via /sys/class/net."""
        try:
            out = subprocess.check_output(["/usr/sbin/iw", "dev"], text=True,
                                          stderr=subprocess.DEVNULL)
        except Exception:
            return None
        # Parse `iw dev` blocks of the form:
        #   phy#0
        #     Interface wlan1
        #       ...
        cur_phy = None
        ifaces = []  # [(phy_id, iface_name)]
        for line in out.splitlines():
            line = line.rstrip()
            if line.startswith("phy#"):
                cur_phy = line.strip()[4:]
            elif line.strip().startswith("Interface "):
                ifaces.append((cur_phy, line.strip().split()[1]))
        for phy, name in ifaces:
            try:
                pinfo = subprocess.check_output(
                    ["/usr/sbin/iw", "phy", f"phy{phy}", "info"],
                    text=True, stderr=subprocess.DEVNULL)
            except Exception:
                continue
            # The "Supported interface modes:" block has one mode per line.
            # We just look for 'monitor' in the section after that header.
            if "Supported interface modes" in pinfo:
                tail = pinfo.split("Supported interface modes", 1)[1]
                # cut off at the next blank header to keep the test tight
                tail = tail.split("\n\n", 1)[0]
                if "* monitor" in tail:
                    return name
        return None

    def _init_log(self):
        try:
            self.loot_dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "w", newline="") as f:
                f.write("WigleWifi-1.4,appRelease=NeoBoX-PRO-3.5,model=Handheld,release=0.1,device=NeoBoX,display=None,board=None,brand=Neo\n")
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
        # Honest guard: monitor mode needs a capable adapter (Alfa AWUS036ACS).
        # _pick_monitor_iface scans every phy's supported modes — if nothing
        # qualifies, we say so instead of pretending monitor is active.
        if not self.wifi_iface:
            self.log_buffer.append("[!] no monitor-capable iface")
            self.log_buffer.append("[!] plug in Alfa AWUS036ACS")
            self.log_buffer.append("[!] WiFi scan disabled")
            return

        # Warn if we're about to flip the iface that's carrying the default
        # route. Monitor mode disconnects it from any AP — internet, SSH and
        # the web UI all drop until B is pressed and managed mode is restored.
        self._iface_was_default_route = self._iface_is_default_route(self.wifi_iface)
        if self._iface_was_default_route:
            self.log_buffer.append(f"[!] {self.wifi_iface} is your internet")
            self.log_buffer.append("[!] WiFi/SSH will drop until exit")

        # NOTE: do NOT set monitor mode via `iw` first. hcxdumptool 6.x
        # explicitly tells you not to ("Do not set monitor mode by third party
        # tools or third party scripts!") — it sets its own. Pre-setting can
        # leave the iface stuck in a bad state if hcxdumptool then exits.

        self.log_buffer.append(f"[*] using {self.wifi_iface} (monitor)")

        # hcxdumptool 6.x flags. `--enable_status=1` and `--active_beacon`
        # were renamed/removed between 5.x and 6.x:
        #   -F           : enable active scanning (broadcast probe-reqs)
        #   --rds=1      : real-time display, sorted by last status
        cmd = [
            "sudo", "hcxdumptool",
            "-i", self.wifi_iface,
            "-w", str(self.pcap_path),
            "-F",
            "--rds=1",
        ]
        try:
            # Fire-and-forget. hcxdumptool 6.x prints setup/status text on
            # stdout, not a stream of "BSSID:" lines we can match — the actual
            # APs only live in the pcap. _verification_loop polls the pcap
            # with hcxpcapngtool every few seconds and updates the counters
            # from there, so we don't need a stdout parser at all.
            self._wifi_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            self.log_buffer.append(f"[!] hcxdumptool failed: {exc}")

    def _verification_loop(self):
        # Single source of truth for the on-screen counters: run hcxpcapngtool
        # against the live pcap every few seconds and pull the summary numbers
        # out of its text. The pcap is the only place 6.x's actual capture
        # data shows up — there's no "live AP list" on stdout to grep.
        ap_re      = re.compile(r"ESSID \(total unique\)\.+:\s*(\d+)")
        eapol_re   = re.compile(r"EAPOL M1 messages \(total\)\.+:\s*(\d+)")
        pmkid_re   = re.compile(r"PMKID \(total\)\.+:\s*(\d+)")
        beacon_re  = re.compile(r"BEACON \(total\)\.+:\s*(\d+)")
        while not self._stop_event.is_set():
            if self.pcap_path.exists() and self.pcap_path.stat().st_size > 256:
                try:
                    cmd = ["hcxpcapngtool", str(self.pcap_path)]
                    out = subprocess.check_output(
                        cmd, text=True, stderr=subprocess.STDOUT,
                        timeout=8)
                    ap = ap_re.search(out)
                    eapol = eapol_re.search(out)
                    pmkid = pmkid_re.search(out)
                    new_aps = int(ap.group(1)) if ap else 0
                    new_hashes = ((int(eapol.group(1)) if eapol else 0) +
                                  (int(pmkid.group(1)) if pmkid else 0))
                    if new_aps > self.aps_found:
                        # Log just the delta so the buffer doesn't spam-fill.
                        delta = new_aps - self.aps_found
                        self.log_buffer.append(f"[W] +{delta} AP "
                                               f"({new_aps} total)")
                        self.aps_found = new_aps
                    if new_hashes > self.verified_hashes:
                        self.log_buffer.append(f"[*] HASH CAPTURED: {new_hashes}")
                        self.verified_hashes = new_hashes
                except Exception:
                    pass
            time.sleep(5)

    def _bt_engine(self):
        # Prefer hci1 (USB BT) but fall back to hci0 (Pi's onboard) — unlike WiFi,
        # using the onboard BT for scanning doesn't break the rest of the device.
        if not os.path.exists(f"/sys/class/bluetooth/{self.bt_iface}"):
            if os.path.exists("/sys/class/bluetooth/hci0"):
                self.bt_iface = "hci0"
                self.log_buffer.append("[*] BT: using onboard hci0")
            else:
                self.log_buffer.append("[!] no BT controller")
                self.log_buffer.append("[!] BT scan disabled")
                return

        subprocess.run(["sudo", "bluetoothctl", "power", "on"], capture_output=True)
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
                            self.log_buffer.append(f"[B] {name[:10]} | {self._get_vendor(mac)}")
                subprocess.run(["sudo", "timeout", "2s", "hcitool", "-i", self.bt_iface, "lescan"], capture_output=True)
            except: pass
            time.sleep(2)

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
        if self._wifi_proc:
            self._wifi_proc.terminate()
        subprocess.run(["sudo", "pkill", "-f", "hcxdumptool"], capture_output=True)
        # Restore the iface: bring it back to managed mode and let
        # NetworkManager reconnect. Skip the restore if we never actually
        # opened it (no iface was monitor-capable in the first place).
        if self.wifi_iface:
            subprocess.run(["sudo", "ip", "link", "set", self.wifi_iface, "down"],
                           capture_output=True)
            subprocess.run(["sudo", "/usr/sbin/iw", "dev", self.wifi_iface,
                            "set", "type", "managed"], capture_output=True)
            subprocess.run(["sudo", "ip", "link", "set", self.wifi_iface, "up"],
                           capture_output=True)
            # Only nudge NM if we just nuked the default route — otherwise
            # we'd needlessly bounce a working connection.
            if getattr(self, "_iface_was_default_route", False):
                subprocess.run(["sudo", "nmcli", "device", "connect",
                                self.wifi_iface], capture_output=True)

    def on_action(self, action: str):
        if action == "B":
            self._stop_all()
            self.app.pop()

    def update(self, dt: float):
        # Update signal density history every second
        now = time.time()
        if now - self._last_graph_update >= 1.0:
            # Signal density = total new devices in last second (approx)
            self.signal_history.append(len(self._seen_macs) + len(self._seen_bt))
            self._last_graph_update = now

    def is_animating(self):
        return True

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "RECON: WARDRIVING PRO 3.5")

        accent = theme.color("accent")
        accent2 = theme.color("accent2")
        dim = theme.color("text_dim")
        ui, small = theme.font("ui"), theme.font("small")
        title_f = theme.font("title")
        
        # 1. GPS (Top Left)
        link_rect = pygame.Rect(10, 40, 160, 110)
        pygame.draw.rect(surf, theme.color("tile"), link_rect, border_radius=8)
        pygame.draw.rect(surf, accent if self.linked else dim, link_rect, width=1, border_radius=8)
        
        if not self.linked:
            if hasattr(self, 'qr_surf'):
                surf.blit(self.qr_surf, (link_rect.centerx - self.qr_surf.get_width()//2, link_rect.y + 5))
            surf.blit(render_text(small, "PHONE GPS LINK", accent), (link_rect.x + 35, link_rect.bottom - 18))
        else:
            surf.blit(render_text(small, "GPS LINK: ACTIVE", theme.color("danger")), (link_rect.x + 10, link_rect.y + 8))
            surf.blit(render_text(ui, f"LAT: {self.gps['lat']:.5f}", theme.color("text")), (link_rect.x + 10, link_rect.y + 30))
            surf.blit(render_text(ui, f"LON: {self.gps['lon']:.5f}", theme.color("text")), (link_rect.x + 10, link_rect.y + 52))
            pygame.draw.rect(surf, (0,0,0), (link_rect.x + 10, link_rect.y + 85, 140, 4))
            acc_w = max(2, 140 - int(self.gps['acc'] * 2))
            pygame.draw.rect(surf, accent, (link_rect.x + 10, link_rect.y + 85, min(140, acc_w), 4))
            surf.blit(render_text(small, f"ACCURACY: {self.gps['acc']:.1f}m", dim), (link_rect.x + 10, link_rect.y + 92))

        # 2. STATS & GRAPH (Right)
        stats_rect = pygame.Rect(180, 40, config.SCREEN_W - 190, 110)
        pygame.draw.rect(surf, theme.color("tile"), stats_rect, border_radius=8)
        pygame.draw.rect(surf, accent, stats_rect, width=1, border_radius=8)
        
        surf.blit(render_text(small, "WIFI", dim), (stats_rect.x + 10, stats_rect.y + 5))
        surf.blit(render_text(title_f, str(self.aps_found), accent), (stats_rect.x + 10, stats_rect.y + 18))
        
        surf.blit(render_text(small, "BT", dim), (stats_rect.x + 75, stats_rect.y + 5))
        surf.blit(render_text(title_f, str(self.bt_found), accent2), (stats_rect.x + 75, stats_rect.y + 18))

        surf.blit(render_text(small, "HASHES", dim), (stats_rect.x + 140, stats_rect.y + 5))
        h_color = theme.color("danger") if self.verified_hashes > 0 else dim
        surf.blit(render_text(title_f, str(self.verified_hashes), h_color), (stats_rect.x + 140, stats_rect.y + 18))

        # Signal Density Graph
        graph_rect = pygame.Rect(stats_rect.x + 10, stats_rect.y + 60, stats_rect.width - 20, 40)
        pygame.draw.rect(surf, (0,0,0, 100), graph_rect)
        if len(self.signal_history) > 1:
            max_v = max(max(self.signal_history), 5)
            pts = []
            for i, val in enumerate(self.signal_history):
                x = graph_rect.x + (i * (graph_rect.width / 59))
                y = graph_rect.bottom - (val / max_v * graph_rect.height)
                pts.append((x, y))
            pygame.draw.lines(surf, accent, False, pts, 1)

        # 3. LIVE LOG (Bottom)
        log_rect = pygame.Rect(10, 160, config.SCREEN_W - 20, config.SCREEN_H - 195)
        pygame.draw.rect(surf, (0, 0, 0, 200), log_rect, border_radius=8)
        pygame.draw.rect(surf, accent, log_rect, width=1, border_radius=8)
        
        y = log_rect.y + 5
        for entry in self.log_buffer:
            col = theme.color("text")
            if "[W]" in entry: col = accent
            if "[B]" in entry: col = accent2
            if "[*]" in entry: col = theme.color("danger")
            surf.blit(render_text(small, entry, col), (log_rect.x + 10, y))
            y += 14

    def hints(self):
        return [("B", "stop & exit")]
