"""Application core: window/scaling, screen stack, input routing, main loop."""
from __future__ import annotations

import queue
import time
import struct

import pygame

from . import assets, config, theme as theme_mod
from .inputs import KeyboardBackend
from .ui import statusbar
from .font_cache import render_text

HINT_H = 24

class App:
    def __init__(self, mode: str = "windowed", scale: int = 2,
                 theme_name: str = config.DEFAULT_THEME, use_gpio: bool = False):
        print("[DEBUG] App.__init__ starting")
        self.mode = mode
        self.scale = scale
        self.running = True
        self.theme = theme_mod.load(theme_name)
        self._wallpaper_cache = None
        self._wallpaper_key = None

        self._init_window()
        self.logical = pygame.Surface((config.SCREEN_W, config.SCREEN_H))

        self.statusbar = statusbar.StatusBar()
        self.keyboard = KeyboardBackend()
        from .audiofx import Sfx
        self.sfx = Sfx(enabled=(mode != "headless"))
        self.action_queue: queue.Queue[str] = queue.Queue()
        self.use_gpio = use_gpio
        self.gpio = None
        if use_gpio:
            self._init_gpio()
        
        self._init_remote_listener()
        self._init_live_view_server()

        self.stack: list = []
        self.clock = pygame.time.Clock()
        self._transition = None   # {old_surf, offset, direction, speed}
        self._section_cache: dict[str, object] = {}   # lazy SectionScreen reuse

    def open_section(self, section: dict):
        """Push a section screen, reusing it across opens so the second time
        is instant (no payload rediscovery / no widget rebuild). BigBox feel."""
        sid = section.get("id", section.get("name", ""))
        scr = self._section_cache.get(sid)
        if scr is None:
            from .screens.section import SectionScreen
            scr = SectionScreen(self, section)
            self._section_cache[sid] = scr
        self.push(scr)

    def _init_remote_listener(self):
        import socket
        import threading
        def _listen():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind(("127.0.0.1", 9999))
                while self.running:
                    data, addr = sock.recvfrom(1024)
                    action = data.decode().strip()
                    if action: self.action_queue.put(action)
            except: pass
            finally: sock.close()
        threading.Thread(target=_listen, daemon=True).start()

    def _init_live_view_server(self):
        import socket
        import threading
        import io
        def _serve():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", 9998))
                sock.listen(1)
                while self.running:
                    conn, addr = sock.accept()
                    try:
                        buf = io.BytesIO()
                        pygame.image.save(self.logical, buf, "jpg")
                        data = buf.getvalue()
                        conn.sendall(struct.pack(">I", len(data)) + data)
                    except: pass
                    finally: conn.close()
            except: pass
            finally: sock.close()
        threading.Thread(target=_serve, daemon=True).start()

    def _init_window(self):
        flags = pygame.SCALED
        if self.mode == "fullscreen":
            self.window = pygame.display.set_mode((config.SCREEN_W, config.SCREEN_H), flags | pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
        elif self.mode == "headless":
            self.window = pygame.display.set_mode((config.SCREEN_W, config.SCREEN_H))
        else:
            self.window = pygame.display.set_mode((config.SCREEN_W, config.SCREEN_H), flags)
        pygame.display.set_caption("Neo")

    def _init_gpio(self):
        try:
            from .inputs import GpioBackend
            self.gpio = GpioBackend(config.BUTTONS_FILE, self.action_queue.put)
            self.gpio.start()
        except: pass

    def pause_gpio(self):
        if self.gpio:
            self.gpio.stop()
            self.gpio = None

    def resume_gpio(self):
        if self.use_gpio and self.gpio is None: self._init_gpio()

    def enter_game_mode(self):
        self.pause_gpio()
        self._suspend_render = True

    def exit_game_mode(self):
        self._suspend_render = False
        self._dirty = True
        import subprocess
        subprocess.run(["sudo", "-n", "pkill", "-f", "keybridge.py"], capture_output=True)
        self.resume_gpio()

    def push(self, screen):
        # Capture current screen for transition
        old_surf = self.logical.copy()
        self.stack.append(screen)
        self._transition = {"surf": old_surf, "pos": 0.0, "dir": 1} # 1 = sliding in

    def pop(self):
        if len(self.stack) > 1:
            old_surf = self.logical.copy()
            self.stack.pop()
            self._transition = {"surf": old_surf, "pos": 0.0, "dir": -1} # -1 = sliding out

    @property
    def current(self):
        return self.stack[-1]

    def quit(self):
        self.running = False

    def go_home(self):
        from .screens.home import HomeScreen
        self.stack = [HomeScreen(self)]

    def set_theme(self, name: str):
        self.theme = theme_mod.load(name)
        self._wallpaper_cache = None

    def cycle_theme(self):
        names = sorted(p.stem for p in config.THEMES_DIR.glob("*.json"))
        if not names: return
        i = names.index(self.theme.name) if self.theme.name in names else -1
        self.set_theme(names[(i + 1) % len(names)])

    def run_payload(self, meta: dict):
        screen_req = meta.get("screen")
        if screen_req == "youtube":
            from .screens.youtube import YoutubeSearchScreen
            self.push(YoutubeSearchScreen(self, meta))
        elif screen_req == "cctv":
            from .screens.cctv import CctvGalleryScreen
            self.push(CctvGalleryScreen(self))
        elif screen_req == "pwnagotchi":
            from .screens.pwnagotchi import PwnagotchiScreen
            self.push(PwnagotchiScreen(self, meta))
        elif screen_req == "loot":
            from .screens.loot import LootScreen
            self.push(LootScreen(self))
        elif screen_req == "ble_spam":
            from .screens.ble_spam import BLESpamScreen
            self.push(BLESpamScreen(self))
        elif screen_req == "bad_ble":
            from .screens.bad_ble import BadBLEScreen
            self.push(BadBLEScreen(self))
        elif screen_req == "wardrive":
            from .screens.wardriving import WardrivingScreen
            self.push(WardrivingScreen(self))
        elif meta.get("roms"):
            from .screens.rompicker import RomPickerScreen
            self.push(RomPickerScreen(self, meta))
        elif meta.get("needs"):
            self._collect_params(meta, meta["needs"], {}, lambda p: self.launch_payload(meta, p))
        else:
            self.launch_payload(meta, {})

    def launch_payload(self, meta: dict, params: dict, *args, rom: str | None = None):
        from .payloads import build_command
        from .screens.console import ConsoleScreen
        exclusive = meta.get("input") == "gpio"
        cmd = build_command(meta, params, rom=rom, args=list(args))
        self.push(ConsoleScreen(self, {"name": meta["name"], "cmd": cmd, "mode": "capture"}, exclusive=exclusive))

    def settings_action(self, action: str):
        if action == "theme": self.cycle_theme()
        elif action == "about":
            from .screens.about import AboutScreen
            self.push(AboutScreen(self))
        elif action == "power": self.open_power_menu()
        elif action == "update": self.run_ota()
        elif action == "loot":
            from .screens.loot import LootScreen
            self.push(LootScreen(self))
        elif action == "web_ui": self.show_web_info()
        elif action == "restart_web_ui":
            cmd = "sudo systemctl stop neo-web || true; sudo systemctl start neo-web"
            self.run_command(cmd, "Reset Web")
        elif action == "deps": self.install_deps()
        elif action == "wifi":
            from .screens.wifi import WifiScreen
            self.push(WifiScreen(self))

    def install_deps(self):
        from . import payloads as payloads_mod
        all_p = payloads_mod.list_all_payloads()
        packages = {pkg for p in all_p for pkg in p.get("apt", [])}
        if not packages: return
        pkg_list = " ".join(sorted(packages))
        cmd = f"sudo apt update && sudo apt install -y {pkg_list}"
        self.run_command(cmd, "Deps")

    def show_web_info(self):
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except: ip = "127.0.0.1"
        msg = f"Web UI: http://{ip}:8888"
        self.run_command(f"echo '{msg}'", "Web UI Status")

    def run_ota(self):
        import shlex
        from .screens.console import ConsoleScreen
        script = shlex.quote(str(config.BASE_DIR / "scripts" / "ota_pull.sh"))
        cmd = f"bash {script}"
        self.push(ConsoleScreen(self, {"name": "Update", "cmd": cmd, "mode": "capture"},
                                complete_action=("apply & restart", self.restart)))

    def restart(self):
        import os, sys
        if self.gpio: self.gpio.stop()
        pygame.quit()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _collect_params(self, tool, names, acc, done):
        if not names:
            done(acc)
            return
        from .screens.textinput import OnScreenKeyboard
        name = names[0]
        def on_value(val):
            self.pop()
            acc[name] = val
            self._collect_params(tool, names[1:], acc, done)
        self.push(OnScreenKeyboard(self, f"Enter {name}", on_value, initial=acc.get(name, "")))

    def draw_wallpaper(self, surf, theme):
        wp = theme.wallpaper
        if wp == "gradient":
            if self._wallpaper_cache is None or self._wallpaper_key != theme.name:
                self._wallpaper_cache = assets.vgradient((config.SCREEN_W, config.SCREEN_H), theme.color("bg"), theme.color("bg_alt"))
                self._wallpaper_key = theme.name
            surf.blit(self._wallpaper_cache, (0, 0))
        elif wp:
            img = assets.load_background(wp, (config.SCREEN_W, config.SCREEN_H))
            if img: surf.blit(img, (0, 0))
            else: surf.fill(theme.color("bg"))
        else: surf.fill(theme.color("bg"))

    def _draw_hints(self, surf, theme):
        from .ui import panel
        y0 = config.SCREEN_H - HINT_H
        # bar background + accent rule on top
        pygame.draw.rect(surf, theme.color("bar"), (0, y0, config.SCREEN_W, HINT_H))
        pygame.draw.line(surf, theme.color("accent"), (0, y0), (config.SCREEN_W, y0), 1)
        cy = y0 + HINT_H // 2
        x = 10
        for key, label in self.current.hints():
            x += panel.key_chip(surf, theme, x, cy, key, label)

    _SFX = {"UP": "move", "DOWN": "move", "LEFT": "move", "RIGHT": "move", "L": "move", "R": "move", "A": "select", "B": "back", "MENU": "select", "EXIT": "back"}

    def _dispatch(self, action: str):
        self._dirty = True
        self.sfx.play(self._SFX.get(action))
        scr = self.current
        if not getattr(scr, "modal", False):
            if action == "MENU": self.open_quick_menu(); return
            if action == "EXIT": self.open_power_menu(); return
        scr.on_action(action)

    def open_quick_menu(self):
        from .screens.menu import ListMenu
        items = [("Switch theme", self.cycle_theme), ("About", lambda: self.push(AboutScreen(self))), ("Power…", self.open_power_menu)]
        self.push(ListMenu(self, "MENU", items))

    def open_power_menu(self):
        from .screens.menu import ListMenu
        items = [("Reboot", lambda: self.run_command("sudo reboot", "Reboot")), ("Shutdown", lambda: self.run_command("sudo poweroff", "Shutdown")), ("Quit", self.quit)]
        self.push(ListMenu(self, "POWER", items))

    def run_command(self, cmd: str, name: str = "run"):
        from .screens.console import ConsoleScreen
        self.push(ConsoleScreen(self, {"name": name, "cmd": cmd, "mode": "capture"}))

    def _pump_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT: self.running = False
            for action in self.keyboard.actions_from_event(event): self.action_queue.put(action)
        while not self.action_queue.empty(): self._dispatch(self.action_queue.get())

    def render(self, dt: float):
        self.current.update(dt)
        if getattr(self.current, "overlay", False) and len(self.stack) > 1:
            self.stack[-2].draw(self.logical, self.theme)
        self.current.draw(self.logical, self.theme)
        if not getattr(self.current, "hide_hints", False):
            self._draw_hints(self.logical, self.theme)

    def present(self):
        if self.mode == "headless": return
        if self._transition:
            # Handle the slide transition
            self._transition["pos"] += 0.18  # snappier (~100ms at 60fps)
            if self._transition["pos"] >= 1.0:
                self._transition = None
                self.window.blit(self.logical, (0,0))
            else:
                p = self._transition["pos"]
                # Linear slide
                if self._transition["dir"] == 1: # New screen sliding in from right
                    off = int(config.SCREEN_W * (1.0 - p))
                    self.window.blit(self._transition["surf"], (-int(config.SCREEN_W * p), 0))
                    self.window.blit(self.logical, (off, 0))
                else: # Old screen sliding out to right
                    off = int(config.SCREEN_W * p)
                    self.window.blit(self.logical, (-int(config.SCREEN_W * (1.0 - p)), 0))
                    self.window.blit(self._transition["surf"], (off, 0))
        else:
            self.window.blit(self.logical, (0, 0))
        pygame.display.flip()

    def _target_fps(self) -> int:
        if self._suspend_render: return 5
        if self._transition or self.current.is_animating(): return 60
        return 30

    def run(self):
        self._dirty = True
        self._suspend_render = False
        last_render = 0.0
        while self.running:
            self.clock.tick(self._target_fps())
            if self._suspend_render:
                self._pump_events()
                time.sleep(0.1)
                continue
            try:
                self._pump_events()
                now = time.monotonic()
                if self._dirty or self._transition or self.current.is_animating() or (now - last_render) >= 0.5:
                    self.render(1.0 / 60.0)
                    self.present()
                    self._dirty = False
                    last_render = now
            except Exception:
                import traceback
                traceback.print_exc()
                if len(self.stack) > 1: self.stack.pop()
                else: self.go_home()
                self._dirty = True
        if self.gpio: self.gpio.stop()
        pygame.quit()
