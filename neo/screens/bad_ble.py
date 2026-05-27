"""BadBLE screen — Professional HID injection and live BLE scanning."""
from __future__ import annotations

import os
import subprocess
import threading
import time
import re
from pathlib import Path
from collections import deque

import pygame

from . import Screen
from .. import config

PHASE_SCAN = "scan"
PHASE_SCRIPTS = "scripts"
PHASE_ATTACK = "attack"

class BadBLEScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.phase = PHASE_SCAN
        self.devices = [] # List of dicts: {mac, name, vendor, rssi, seen}
        self.cursor = 0
        self.scripts = []
        self.script_cursor = 0
        self.selected_target = None
        self.selected_script = None
        self.iface = self._get_best_iface()
        
        self.status = "IDLE"
        self.error_msg = ""
        self.log = deque(maxlen=12)
        
        self.script_dir = Path("loot/blescripts")
        self.script_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_sample_script()
        
        self._stop_event = threading.Event()
        self._scan_proc = None
        self._attack_proc = None
        
        self._start_live_scan()

    def _get_best_iface(self) -> str:
        try:
            out = subprocess.check_output(["hciconfig"]).decode()
            if "hci1" in out: return "hci1"
        except: pass
        return "hci0"

    def _ensure_sample_script(self):
        sample = self.script_dir / "hello.txt"
        if not sample.exists():
            with open(sample, "w") as f:
                f.write("GUI r\nDELAY 500\nSTRING notepad.exe\nENTER\nDELAY 1000\nSTRING Hello from NeoBoX BadBLE!\nENTER\n")

    def on_action(self, action: str):
        if action == "B":
            if self.phase == PHASE_SCAN:
                self._stop_all()
                self.app.pop()
            elif self.phase == PHASE_SCRIPTS:
                self.phase = PHASE_SCAN
            elif self.phase == PHASE_ATTACK:
                self._stop_all()
                self._start_live_scan()
                self.phase = PHASE_SCAN

        elif action == "UP":
            if self.phase == PHASE_SCAN and self.devices:
                self.cursor = (self.cursor - 1) % len(self.devices)
            elif self.phase == PHASE_SCRIPTS and self.scripts:
                self.script_cursor = (self.script_cursor - 1) % len(self.scripts)

        elif action == "DOWN":
            if self.phase == PHASE_SCAN and self.devices:
                self.cursor = (self.cursor + 1) % len(self.devices)
            elif self.phase == PHASE_SCRIPTS and self.scripts:
                self.script_cursor = (self.script_cursor + 1) % len(self.scripts)

        elif action == "A":
            if self.phase == PHASE_SCAN and self.devices:
                self.selected_target = self.devices[self.cursor]
                self._stop_all()
                self._load_scripts()
                self.phase = PHASE_SCRIPTS
            elif self.phase == PHASE_SCRIPTS and self.scripts:
                self.selected_script = self.scripts[self.script_cursor]
                self._start_attack()
                self.phase = PHASE_ATTACK

        elif action == "X": # Manual Refresh
            if self.phase == PHASE_SCAN:
                self._stop_all()
                self._start_live_scan()

    def _start_live_scan(self):
        self.devices = []
        self.cursor = 0
        self.status = "SCANNING..."
        self._stop_event.clear()
        threading.Thread(target=self._live_scan_loop, daemon=True).start()

    def _live_scan_loop(self):
        subprocess.run(["sudo", "systemctl", "stop", "bluetooth"], capture_output=True)
        # Use bettercap in interactive mode to stream events
        cmd = ["sudo", "bettercap", "-eval", "ble.recon on", "-no-colors"]
        try:
            self._scan_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            # Regex for new device events: [ble.device.new] new BLE device detected as MAC (Vendor) -RSSI dBm.
            new_dev_re = re.compile(r"new BLE device detected as ([0-9a-fA-F:]{17}) \((.*?)\) (-?\d+) dBm")
            
            for line in self._scan_proc.stdout:
                if self._stop_event.is_set(): break
                
                m = new_dev_re.search(line)
                if m:
                    mac, vendor, rssi = m.group(1), m.group(2), m.group(3)
                    # Check if already in list
                    if not any(d["mac"].lower() == mac.lower() for d in self.devices):
                        self.devices.append({
                            "mac": mac,
                            "name": vendor, # Bettercap often puts name in parens if available
                            "vendor": vendor,
                            "rssi": rssi,
                            "seen": time.strftime("%H:%M:%S")
                        })
                        self.status = f"LIVE SCAN: {len(self.devices)} DEVS"
        except Exception as e:
            self.error_msg = str(e)
        finally:
            self._stop_all()

    def _load_scripts(self):
        self.scripts = sorted([f for f in self.script_dir.glob("*.txt")])
        self.script_cursor = 0

    def _start_attack(self):
        self.status = "ATTACKING..."
        self.log.clear()
        self.log.append(f"TARGET: {self.selected_target['mac']}")
        self.log.append(f"SCRIPT: {self.selected_script.name}")
        threading.Thread(target=self._attack_loop, daemon=True).start()

    def _attack_loop(self):
        subprocess.run(["sudo", "systemctl", "stop", "bluetooth"], capture_output=True)
        mac = self.selected_target["mac"]
        script_path = str(self.selected_script.absolute())
        
        # Aggressive HID injection caplet
        # 1. Recon to find dev
        # 2. Enum to get services
        # 3. Inject HID
        cmd = [
            "sudo", "bettercap", 
            "-eval", f"ble.recon on; ble.enum {mac}; ble.hid.inject {mac} {script_path}; sleep 10; q",
            "-no-colors"
        ]
        try:
            self._attack_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in self._attack_proc.stdout:
                clean = line.strip()
                if clean and not clean.startswith("["): # Filter out some noise
                    self.log.append(clean[:45])
            self.status = "DONE / IDLE"
        except Exception as e:
            self.error_msg = str(e)
            self.status = "ATTACK FAILED"
        finally:
            subprocess.run(["sudo", "systemctl", "start", "bluetooth"], capture_output=True)

    def _stop_all(self):
        self._stop_event.set()
        if self._scan_proc:
            self._scan_proc.terminate()
            self._scan_proc = None
        if self._attack_proc:
            self._attack_proc.terminate()
            self._attack_proc = None

    def update(self, dt: float):
        pass

    def is_animating(self):
        return "..." in self.status or self.phase == PHASE_SCAN

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "BT: BAD_BLE 2.0")

        font = theme.font("ui")
        small = theme.font("small")
        accent = theme.color("accent")
        
        # Header Info
        status_rect = pygame.Rect(10, 40, config.SCREEN_W - 20, 45)
        pygame.draw.rect(surf, theme.color("tile"), status_rect, border_radius=8)
        pygame.draw.rect(surf, accent, status_rect, width=1, border_radius=8)
        
        surf.blit(font.render(self.status, True, accent), (status_rect.x + 12, status_rect.y + 10))
        surf.blit(small.render(f"ADAPTER: {self.iface}", True, theme.color("text_dim")), 
                  (status_rect.right - 100, status_rect.y + 15))

        area = pygame.Rect(10, 95, config.SCREEN_W - 20, config.SCREEN_H - 125)
        
        if self.phase == PHASE_SCAN:
            self._draw_device_list(surf, area, theme)
        elif self.phase == PHASE_SCRIPTS:
            self._draw_script_list(surf, area, theme)
        elif self.phase == PHASE_ATTACK:
            self._draw_attack_log(surf, area, theme)

    def _draw_device_list(self, surf, area, theme):
        if not self.devices:
            txt = theme.font("ui").render("SCANNING FOR TARGETS...", True, theme.color("text_dim"))
            surf.blit(txt, txt.get_rect(center=area.center))
            return

        row_h = 28
        visible = area.height // row_h
        start = max(0, self.cursor - visible // 2)
        
        for i in range(start, min(len(self.devices), start + visible)):
            d = self.devices[i]
            y = area.y + (i - start) * row_h
            sel = (i == self.cursor)
            
            if sel:
                pygame.draw.rect(surf, theme.color("tile_sel"), (area.x, y, area.width, row_h), border_radius=4)
                pygame.draw.rect(surf, theme.color("accent"), (area.x, y, area.width, row_h), width=1, border_radius=4)
            
            # Vendor/Name
            name = d["name"][:20]
            surf.blit(theme.font("ui").render(name, True, theme.color("text")), (area.x + 5, y + 2))
            
            # MAC and RSSI
            meta = f"{d['mac']} | {d['rssi']}dBm"
            surf.blit(theme.font("small").render(meta, True, theme.color("text_dim")), (area.right - 180, y + 6))

    def _draw_script_list(self, surf, area, theme):
        if not self.scripts:
            txt = theme.font("ui").render("NO SCRIPTS IN loot/blescripts/", True, theme.color("text_dim"))
            surf.blit(txt, txt.get_rect(center=area.center))
            return

        row_h = 24
        for i, s in enumerate(self.scripts):
            y = area.y + i * row_h
            sel = (i == self.script_cursor)
            if sel:
                pygame.draw.rect(surf, theme.color("tile_sel"), (area.x, y, area.width, row_h), border_radius=4)
            
            col = theme.color("accent") if sel else theme.color("text")
            surf.blit(theme.font("ui").render(s.name, True, col), (area.x + 10, y + 2))

    def _draw_attack_log(self, surf, area, theme):
        # Draw target info box
        pygame.draw.rect(surf, (0, 0, 0, 100), area)
        y = area.y + 5
        for line in self.log:
            surf.blit(theme.font("small").render(line, True, theme.color("text")), (area.x + 5, y))
            y += 16

    def hints(self):
        h = [("B", "back")]
        if self.phase == PHASE_SCAN:
            h += [("A", "select"), ("X", "refresh")]
        elif self.phase == PHASE_SCRIPTS:
            h += [("A", "inject")]
        return h
