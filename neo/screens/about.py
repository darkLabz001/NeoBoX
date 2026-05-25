"""About screen: version + device info."""
from __future__ import annotations

import platform
import socket
import subprocess

from . import Screen
from .. import __version__, config
from ..ui import statusbar


def _git_version() -> str:
    try:
        out = subprocess.run(["git", "-C", str(config.BASE_DIR), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=2)
        h = out.stdout.strip()
        return h or "—"
    except Exception:
        return "—"


class AboutScreen(Screen):
    title = "ABOUT"

    def __init__(self, app):
        super().__init__(app)
        try:
            host = socket.gethostname()
        except Exception:
            host = "?"
        self.lines = [
            ("NEOBOX", "accent"),
            (f"firmware v{__version__}  ({_git_version()})", "text_dim"),
            ("", "text"),
            (f"host    {host}", "text"),
            (f"python  {platform.python_version()}", "text"),
            (f"machine {platform.machine()}", "text"),
            (f"theme   {app.theme.name}", "text"),
            ("", "text"),
            ("A pentesting handheld UI", "text_dim"),
        ]

    def on_action(self, action: str):
        if action in ("B", "MENU", "EXIT"):
            self.app.pop()

    def draw(self, surf, theme):
        self.app.draw_wallpaper(surf, theme)
        self.app.statusbar.draw(surf, theme, self.title)
        y = statusbar.HEIGHT + 24
        for text, ckey in self.lines:
            font = theme.font("title", bold=True) if ckey == "accent" else theme.font("ui")
            surf.blit(font.render(text, True, theme.color(ckey)), (16, y))
            y += font.get_height() + 6

    def hints(self):
        return [("B", "back")]
