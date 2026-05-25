"""Application core: window/scaling, screen stack, input routing, main loop."""
from __future__ import annotations

import queue
import time

import pygame

from . import assets, config, theme as theme_mod
from .inputs import KeyboardBackend
from .ui import statusbar

HINT_H = 24


class App:
    def __init__(self, mode: str = "windowed", scale: int = 2,
                 theme_name: str = config.DEFAULT_THEME, use_gpio: bool = False):
        self.mode = mode
        self.scale = scale
        self.running = True
        self.theme = theme_mod.load(theme_name)
        self._wallpaper_cache = None
        self._wallpaper_key = None

        self._init_window()
        self.logical = pygame.Surface((config.SCREEN_W, config.SCREEN_H)).convert()

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

        self.stack: list = []
        self.clock = pygame.time.Clock()

    def _init_remote_listener(self):
        """Start a UDP listener for remote actions (Web UI)."""
        import socket
        import threading
        def _listen():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind(("127.0.0.1", 9999))
                while self.running:
                    data, addr = sock.recvfrom(1024)
                    action = data.decode().strip()
                    if action:
                        self.action_queue.put(action)
            except Exception as e:
                print(f"[remote] listener error: {e}")
            finally:
                sock.close()
        
        t = threading.Thread(target=_listen, daemon=True)
        t.start()
        print("[remote] listener started on port 9999")

    # --- window ---------------------------------------------------------
    def _init_window(self):
        if self.mode == "fullscreen":
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
        elif self.mode == "headless":
            self.window = pygame.display.set_mode((config.SCREEN_W, config.SCREEN_H))
        else:
            self.window = pygame.display.set_mode(
                (config.SCREEN_W * self.scale, config.SCREEN_H * self.scale))
        pygame.display.set_caption("Neo")

    def _init_gpio(self):
        try:
            from .inputs import GpioBackend
            self.gpio = GpioBackend(config.BUTTONS_FILE, self.action_queue.put)
            self.gpio.start()
            print("[gpio] backend started")
        except Exception as exc:
            print(f"[gpio] disabled: {exc}")

    def pause_gpio(self):
        """Release the GPIO lines so an external game's key bridge can claim them."""
        if self.gpio:
            self.gpio.stop()
            self.gpio = None
            print("[gpio] paused")

    def resume_gpio(self):
        if self.use_gpio and self.gpio is None:
            self._init_gpio()

    # --- screen stack ---------------------------------------------------
    def push(self, screen):
        self.stack.append(screen)

    def pop(self):
        if len(self.stack) > 1:
            self.stack.pop()

    @property
    def current(self):
        return self.stack[-1]

    def quit(self):
        self.running = False

    def go_home(self):
        """Replace the whole stack with a fresh home screen (used after the intro)."""
        from .screens.home import HomeScreen
        self.stack = [HomeScreen(self)]

    # --- behaviours screens call ---------------------------------------
    def set_theme(self, name: str):
        self.theme = theme_mod.load(name)
        self._wallpaper_cache = None

    def cycle_theme(self):
        names = sorted(p.stem for p in config.THEMES_DIR.glob("*.json"))
        if not names:
            return
        i = names.index(self.theme.name) if self.theme.name in names else -1
        self.set_theme(names[(i + 1) % len(names)])

    def run_payload(self, meta: dict):
        from .payloads import build_command
        from .screens.console import ConsoleScreen

        exclusive = meta.get("input") == "gpio"

        def go(params: dict):
            cmd = build_command(meta, params)
            self.push(ConsoleScreen(self, {"name": meta["name"], "cmd": cmd, "mode": "capture"},
                                    exclusive=exclusive))

        needs = meta.get("needs", [])
        if needs:
            self._collect_params(meta, needs, {}, go)
        else:
            go({})

    def settings_action(self, action: str):
        if action == "theme":
            self.cycle_theme()
        elif action == "about":
            from .screens.about import AboutScreen
            self.push(AboutScreen(self))
        elif action == "power":
            self.open_power_menu()
        elif action == "update":
            self.run_ota()
        elif action == "web_ui":
            self.show_web_info()
        elif action == "web_ui_log":
            self.run_command(f"sudo journalctl -u neo-web -n 50", "Web Log")
        elif action == "restart_web_ui":
            cmd = (
                "sudo systemctl stop neo-web || true; "
                "sudo systemd-run --unit=neo-web --setenv=PYTHONPATH=$PYTHONPATH:/usr/local/lib/python3.13/dist-packages python3 /home/kali/neo/web/server.py; "
                "echo 'Web UI restarted via systemd-run. Check Web UI for address.'"
            )
            self.run_command(cmd, "Reset Web")
        elif action == "deps":
            self.install_deps()
        elif action == "volume":
            from .screens.volume import VolumeScreen
            self.push(VolumeScreen(self))
        elif action == "wifi":
            from .screens.wifi import WifiScreen
            self.push(WifiScreen(self))

    def install_deps(self):
        """Scan all payloads for 'neo-apt' requirements and install them."""
        from . import payloads as payloads_mod
        all_p = payloads_mod.list_all_payloads()
        packages = set()
        for p in all_p:
            for pkg in p.get("apt", []):
                packages.add(pkg)

        if not packages:
            self.run_command("echo 'No specific dependencies found in payloads.'", "Deps")
            return

        pkg_list = " ".join(sorted(packages))
        cmd = (
            "echo 'Updating package list...' && sudo apt update && "
            f"echo 'Installing: {pkg_list}' && "
            f"sudo apt install -y {pkg_list} && "
            "echo && echo 'All dependencies installed.'"
        )
        self.run_command(cmd, "Deps")

    def show_web_info(self):
        import socket
        import subprocess
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = "127.0.0.1"

        # Check if process is alive
        is_running = subprocess.call("pgrep -f 'web/server.py' > /dev/null", shell=True) == 0
        status = "[RUNNING]" if is_running else "[NOT RUNNING]"

        msg = f"Web UI Status: {status}\\nAddress: http://{ip}:8888\\n\\n"
        if not is_running:
            msg += "DIAGNOSTIC: Server failed to start.\\nCheck 'Web Log' for errors."
        else:
            msg += "Terminal & ROM Uploads active."

        self.run_command(f"echo -e '{msg}'", "Web UI Status")


    def run_ota(self):
        import shlex
        from .screens.console import ConsoleScreen
        base = shlex.quote(str(config.BASE_DIR))
        cmd = (
            f"cd {base} && echo 'Checking for updates...' && "
            "git fetch --quiet origin && BEFORE=$(git rev-parse HEAD) && "
            "git pull --ff-only && AFTER=$(git rev-parse HEAD) && echo && "
            "if [ \"$BEFORE\" = \"$AFTER\" ]; then echo 'Already up to date.'; "
            "else echo 'Updated — press A to apply and restart.'; fi"
        )
        self.push(ConsoleScreen(self, {"name": "Update", "cmd": cmd, "mode": "capture"},
                                complete_action=("apply & restart", self.restart)))

    def restart(self):
        """Re-exec in place so a freshly-pulled version loads in the same session."""
        import os
        import sys
        if self.gpio:
            self.gpio.stop()
        pygame.quit()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _collect_params(self, tool, names, acc, done):
        """Chain an on-screen keyboard per {placeholder}, then call done(acc)."""
        if not names:
            done(acc)
            return
        from .screens.textinput import OnScreenKeyboard
        name = names[0]

        def on_value(val):
            self.pop()                      # close the keyboard
            acc[name] = val
            self._collect_params(tool, names[1:], acc, done)

        self.push(OnScreenKeyboard(self, f"Enter {name}", on_value,
                                   initial=acc.get(name, "")))

    def draw_wallpaper(self, surf, theme):
        wp = theme.wallpaper
        if wp == "gradient":
            key = theme.name
            if self._wallpaper_cache is None or self._wallpaper_key != key:
                self._wallpaper_cache = assets.vgradient(
                    (config.SCREEN_W, config.SCREEN_H),
                    theme.color("bg"), theme.color("bg_alt"))
                self._wallpaper_key = key
            surf.blit(self._wallpaper_cache, (0, 0))
        elif wp:
            img = assets.load_background(wp, (config.SCREEN_W, config.SCREEN_H))
            if img is not None:
                surf.blit(img, (0, 0))
            else:
                surf.fill(theme.color("bg"))
        else:
            surf.fill(theme.color("bg"))

    # --- hint bar -------------------------------------------------------
    def _draw_hints(self, surf, theme):
        y0 = config.SCREEN_H - HINT_H
        pygame.draw.rect(surf, theme.color("bar"), (0, y0, config.SCREEN_W, HINT_H))
        pygame.draw.line(surf, theme.color("text_dim"), (0, y0), (config.SCREEN_W, y0), 1)
        font = theme.font("small")
        x = 10
        for key, label in self.current.hints():
            kt = font.render(key, True, theme.color("accent"))
            surf.blit(kt, (x, y0 + HINT_H // 2 - kt.get_height() // 2))
            x += kt.get_width() + 4
            lt = font.render(label, True, theme.color("text_dim"))
            surf.blit(lt, (x, y0 + HINT_H // 2 - lt.get_height() // 2))
            x += lt.get_width() + 14

    # --- frame ----------------------------------------------------------
    _SFX = {"UP": "move", "DOWN": "move", "LEFT": "move", "RIGHT": "move",
            "L": "move", "R": "move", "A": "select", "B": "back",
            "MENU": "select", "EXIT": "back"}

    def _dispatch(self, action: str):
        self._dirty = True
        self.sfx.play(self._SFX.get(action))
        scr = self.current
        # MENU/EXIT are global overlays unless the active screen is modal.
        if not getattr(scr, "modal", False):
            if action == "MENU":
                self.open_quick_menu()
                return
            if action == "EXIT":
                self.open_power_menu()
                return
        scr.on_action(action)

    # --- overlays -------------------------------------------------------
    def open_quick_menu(self):
        from .screens.menu import ListMenu
        from .screens.about import AboutScreen
        items = [
            ("Switch theme", self.cycle_theme),
            ("About", lambda: self.push(AboutScreen(self))),
            ("Power…", self.open_power_menu),
        ]
        self.push(ListMenu(self, "MENU", items))

    def open_power_menu(self):
        from .screens.menu import ListMenu
        items = [
            ("Reboot", lambda: self.run_command("sudo systemctl reboot", "Reboot")),
            ("Shutdown", lambda: self.run_command("sudo systemctl poweroff", "Shutdown")),
            ("Quit to desktop", self.quit),
        ]
        self.push(ListMenu(self, "POWER", items))

    def run_command(self, cmd: str, name: str = "run"):
        from .screens.console import ConsoleScreen
        self.push(ConsoleScreen(self, {"name": name, "cmd": cmd, "mode": "capture"}))

    def _pump_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            for action in self.keyboard.actions_from_event(event):
                self.action_queue.put(action)
        while not self.action_queue.empty():
            self._dispatch(self.action_queue.get())

    def render(self, dt: float):
        self.current.update(dt)
        if getattr(self.current, "overlay", False) and len(self.stack) > 1:
            self.stack[-2].draw(self.logical, self.theme)   # backdrop
        self.current.draw(self.logical, self.theme)
        if not getattr(self.current, "hide_hints", False):
            self._draw_hints(self.logical, self.theme)

    def present(self):
        if self.mode == "headless":
            return
        win_w, win_h = self.window.get_size()
        if self.mode == "fullscreen":
            # Stretch to fill the panel. On the Game HAT the HDMI board rescales
            # to the 480x320 panel anyway, so a fast (nearest) scale is fine here
            # and far cheaper than smoothscale on the Pi 3B+ (keeps CPU/audio sane).
            scaled = pygame.transform.scale(self.logical, (win_w, win_h))
            self.window.blit(scaled, (0, 0))
        else:
            scale = min(win_w / config.SCREEN_W, win_h / config.SCREEN_H)
            size = (int(config.SCREEN_W * scale), int(config.SCREEN_H * scale))
            scaled = pygame.transform.smoothscale(self.logical, size)
            self.window.fill((0, 0, 0))
            self.window.blit(scaled, ((win_w - size[0]) // 2, (win_h - size[1]) // 2))
        pygame.display.flip()

    def run(self):
        # Render on demand: only redraw when something changed, an animation is
        # running, or ~1/s for the clock. Keeps the Pi 3B+ near-idle on static
        # screens so pipewire never underruns (no system-wide audio crackle).
        self._dirty = True
        last_render = 0.0
        while self.running:
            self.clock.tick(config.FPS)
            self._pump_events()
            now = time.monotonic()
            animating = getattr(self.current, "is_animating", lambda: False)()
            if self._dirty or animating or (now - last_render) >= 0.5:
                self.render(1.0 / config.FPS)
                self.present()
                self._dirty = False
                last_render = now
        if self.gpio:
            self.gpio.stop()
        pygame.quit()

    # --- offscreen snapshot for dev preview -----------------------------
    def snapshot(self, path: str, actions: list[str] | None = None, settle: int = 12):
        for a in (actions or []):
            self._dispatch(a)
        for _ in range(settle):           # let scroll animations settle
            self.render(1 / config.FPS)
        pygame.image.save(self.logical, path)
        print(f"[snapshot] saved {path}")
