"""Discover and describe `.py` payloads under payloads/<section>/.

A payload is just a Python script. The UI reads optional metadata from header
comments (no code execution) to build its tile and prompt for inputs:

    #!/usr/bin/env python3
    # neo-name: Quick Nmap
    # neo-desc: Fast scan of common ports
    # neo-needs: target
    # neo-icon: recon
    ...

It is run with `python3 <file> <inputs...>` and the inputs are also exported as
NEO_<NAME> environment variables. Drop a new .py in a section folder and it
appears automatically — that's how users add custom payloads.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from . import config

_HEADER = re.compile(r"^#\s*neo-(\w+)\s*:\s*(.*)$")


def section_dir(section_id: str) -> Path:
    return config.PAYLOADS_DIR / section_id


def prettify(stem: str) -> str:
    return stem.replace("_", " ").replace("-", " ").strip().title()


def parse_meta(path: Path) -> dict:
    meta = {"path": str(path), "name": prettify(path.stem),
            "desc": "", "needs": [], "icon": None, "input": None, "apt": [],
            "roms": None, "romext": []}
    try:
        with open(path, "r", errors="replace") as fh:
            for _ in range(40):
                line = fh.readline()
                if not line:
                    break
                m = _HEADER.match(line.strip())
                if not m:
                    continue
                key, val = m.group(1).lower(), m.group(2).strip()
                if key == "name":
                    meta["name"] = val
                elif key == "desc":
                    meta["desc"] = val
                elif key == "icon":
                    meta["icon"] = val
                elif key == "needs":
                    meta["needs"] = [x.strip() for x in val.split(",") if x.strip()]
                elif key == "input":
                    meta["input"] = val.strip().lower()
                elif key == "apt":
                    meta["apt"] = [x.strip() for x in val.split(",") if x.strip()]
                elif key == "roms":
                    # ROM subdirectory under ~/roms (e.g. "ps1") -> shows a picker
                    meta["roms"] = val.strip()
                elif key == "romext":
                    # extensions to list (e.g. ".cue .pbp .chd"); normalise to lower w/ dot
                    meta["romext"] = [(e if e.startswith(".") else "." + e).lower()
                                      for e in re.split(r"[,\s]+", val) if e.strip()]
    except Exception:
        pass
    return meta


def list_payloads(section_id: str) -> list[dict]:
    d = section_dir(section_id)
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.py")):
        if f.name.startswith("_"):
            continue
        out.append(parse_meta(f))
    return out


def list_all_payloads() -> list[dict]:
    """Gather every payload across all sections."""
    out = []
    if not config.PAYLOADS_DIR.is_dir():
        return []
    for d in sorted(config.PAYLOADS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            out.extend(list_payloads(d.name))
    return out


def build_command(meta: dict, params: dict, rom: str | None = None) -> str:
    """Compose the shell command to run a payload with collected inputs.

    `rom`, if given, is passed as the first positional arg (argv[1]) — game
    payloads read their ROM path from there.
    """
    env = " ".join(f"NEO_{n.upper()}={shlex.quote(params.get(n, ''))}"
                   for n in meta.get("needs", []))
    parts = []
    if rom:
        parts.append(shlex.quote(rom))
    parts += [shlex.quote(params.get(n, "")) for n in meta.get("needs", [])]
    cmd = f"python3 {shlex.quote(meta['path'])} {' '.join(parts)}".strip()
    return f"{env} {cmd}".strip()
