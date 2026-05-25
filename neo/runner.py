"""Run a shell command in a PTY and stream its output line-by-line.

A PTY makes tools behave as if on a terminal (line buffering, color), and lets
us feed stdin for interactive tools. Output is decoded, ANSI-stripped, and
delivered to callbacks that run on the runner's own thread.
"""
from __future__ import annotations

import os
import pty
import select
import signal
import subprocess
import threading
from typing import Callable

from .util import strip_ansi


class ProcRunner:
    def __init__(self, cmd: str, on_line: Callable[[str], None],
                 on_exit: Callable[[int], None]):
        self.cmd = cmd
        self.on_line = on_line
        self.on_exit = on_exit
        self._master = None
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def write(self, data: str):
        """Send a line of input to the process (interactive tools)."""
        if self._master is not None:
            try:
                os.write(self._master, data.encode())
            except OSError:
                pass

    def stop(self):
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except Exception:
                pass

    def _run(self):
        master, slave = pty.openpty()
        self._master = master
        try:
            self._proc = subprocess.Popen(
                self.cmd, shell=True, stdin=slave, stdout=slave, stderr=slave,
                preexec_fn=os.setsid, close_fds=True,
            )
        except Exception as exc:
            self.on_line(f"[failed to launch: {exc}]")
            self.on_exit(127)
            return
        os.close(slave)

        buf = ""
        while not self._stop.is_set():
            try:
                r, _, _ = select.select([master], [], [], 0.2)
            except (OSError, ValueError):
                break
            if master in r:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk.decode(errors="replace")
                *lines, buf = buf.split("\n")
                for line in lines:
                    self.on_line(strip_ansi(line))
            if self._proc.poll() is not None and master not in r:
                break

        if buf.strip():
            self.on_line(strip_ansi(buf))
        try:
            os.close(master)
        except OSError:
            pass
        code = self._proc.wait() if self._proc else -1
        self.on_exit(code)
