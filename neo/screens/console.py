"""Console screen: runs a tool and streams its live output, scrollable."""
from __future__ import annotations

import time
from collections import deque

import pygame

from . import Screen
from .. import config, util
from ..runner import ProcRunner
from ..ui import statusbar

_SPIN = "|/-\\"


class ConsoleScreen(Screen):
    def __init__(self, app, tool: dict, params: dict | None = None, complete_action=None,
                 exclusive: bool = False):
        super().__init__(app)
        self.tool = tool
        self.title = tool["name"]
        # complete_action: optional (label, callable) shown on A when finished
        self.complete_action = complete_action
        # exclusive: release GPIO while this runs (so a game's key bridge can use it)
        self.exclusive = exclusive
        if exclusive:
            app.pause_gpio()
        self.cmd = util.fill(tool.get("cmd", ""), params or {})
        self.lines: deque[str] = deque(maxlen=2000)
        self.lines.append(f"$ {self.cmd}")
        self.status = "running"
        self.exit_code = None
        self.scroll = 0          # lines scrolled up from the tail
        self._line_h = 0
        self.runner = ProcRunner(self.cmd, self._on_line, self._on_exit)
        self.runner.start()

    # callbacks (runner thread) -----------------------------------------
    def _on_line(self, line: str):
        self.lines.append(line)

    def is_animating(self):
        return self.status == "running"

    def _on_exit(self, code: int):
        self.exit_code = code
        self.status = "done"
        if self.exclusive:
            self.app.resume_gpio()
        self.lines.append("")
        self.lines.append(f"[exited {code}]  press B to go back")

    # input --------------------------------------------------------------
    def on_action(self, action: str):
        if action == "B":
            self.runner.stop()
            if self.exclusive:
                self.app.resume_gpio()
            self.app.pop()
        elif action == "UP":
            self.scroll += 3
        elif action == "DOWN":
            self.scroll = max(0, self.scroll - 3)
        elif action == "L":
            self.scroll += 12
        elif action == "R":
            self.scroll = max(0, self.scroll - 12)
        elif action == "A" and self.status == "done" and self.complete_action:
            self.complete_action[1]()
        elif action == "A" and self.status == "done":
            # rerun
            self.lines.clear()
            self.lines.append(f"$ {self.cmd}")
            self.status = "running"
            self.exit_code = None
            self.scroll = 0
            self.runner = ProcRunner(self.cmd, self._on_line, self._on_exit)
            self.runner.start()

    # draw ---------------------------------------------------------------
    def draw(self, surf, theme):
        surf.fill(theme.color("bg"))
        font = theme.font("small")
        self._line_h = font.get_height() + 1

        top = statusbar.HEIGHT + 2
        bottom = config.SCREEN_H - 24
        area = pygame.Rect(8, top + 2, config.SCREEN_W - 16, bottom - top - 4)
        visible = max(1, area.height // self._line_h)

        all_lines = list(self.lines)
        max_scroll = max(0, len(all_lines) - visible)
        self.scroll = min(self.scroll, max_scroll)
        end = len(all_lines) - self.scroll
        start = max(0, end - visible)

        prev_clip = surf.get_clip()
        surf.set_clip(area)
        y = area.y
        for line in all_lines[start:end]:
            color = theme.color("accent") if line.startswith("$") else (
                theme.color("warn") if line.startswith("[exit") else theme.color("text"))
            surf.blit(font.render(line[:120], True, color), (area.x, y))
            y += self._line_h
        surf.set_clip(prev_clip)

        # scrollbar
        if max_scroll > 0:
            frac = visible / len(all_lines)
            bar_h = max(12, int(area.height * frac))
            pos = (1 - self.scroll / max_scroll) if max_scroll else 1
            by = area.y + int((area.height - bar_h) * pos)
            pygame.draw.rect(surf, theme.color("text_dim"),
                             (area.right + 2, by, 3, bar_h), border_radius=2)

        # status bar (top) with spinner
        title = self.title
        if self.status == "running":
            title = f"{_SPIN[int(time.time() * 8) % 4]} {self.title}"
        self.app.statusbar.draw(surf, theme, title)

    def hints(self):
        if self.status == "done":
            a = self.complete_action[0] if self.complete_action else "rerun"
            return [("A", a), ("B", "back"), ("↑↓", "scroll")]
        return [("B", "stop"), ("↑↓", "scroll")]
