"""Small helpers: ANSI stripping and command templating."""
from __future__ import annotations

import re
import shlex

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text).replace("\r", "")


def placeholders(cmd: str) -> list[str]:
    """Return the {names} a command needs filled in (e.g. target, subnet)."""
    seen = []
    for m in _PLACEHOLDER.finditer(cmd):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def fill(cmd: str, params: dict) -> str:
    def repl(m):
        return params.get(m.group(1), m.group(0))
    return _PLACEHOLDER.sub(repl, cmd)


def needs_sudo(cmd: str) -> bool:
    try:
        return shlex.split(cmd)[0] == "sudo"
    except Exception:
        return cmd.strip().startswith("sudo ")
