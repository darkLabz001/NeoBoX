"""WiFi control via nmcli (scan / connect / disconnect)."""
from __future__ import annotations

import shutil
import subprocess


def available() -> bool:
    return shutil.which("nmcli") is not None


def _run(args, timeout=20):
    return subprocess.run(["nmcli"] + args, capture_output=True, text=True, timeout=timeout)


def scan(rescan: str = "auto") -> list[dict]:
    """Return nearby networks: [{ssid, signal, security, secured, in_use}].

    rescan: 'auto' (rescan only if cache is stale — fast), 'yes' (force), 'no'.
    """
    args = ["-t", "-f", "IN-USE,SIGNAL,SECURITY,SSID", "device", "wifi", "list",
            "--rescan", rescan]
    try:
        out = _run(args, timeout=25).stdout
    except Exception:
        return []
    nets, seen = [], set()
    for line in out.splitlines():
        if not line:
            continue
        parts = line.split(":")
        if len(parts) < 4:
            continue
        in_use = parts[0].strip() == "*"
        signal = int(parts[1]) if parts[1].strip().isdigit() else 0
        security = parts[2].strip()
        ssid = ":".join(parts[3:]).replace("\\:", ":").strip()
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        nets.append({
            "ssid": ssid, "signal": signal, "security": security,
            "secured": bool(security and security not in ("--", "")), "in_use": in_use,
        })
    nets.sort(key=lambda n: (0 if n["in_use"] else 1, -n["signal"]))
    return nets


def connect(ssid: str, password: str | None = None, timeout: int = 45):
    # Delete any stale saved profile for this SSID first — otherwise nmcli reuses
    # an old (possibly wrong-password) profile and fails even with a correct pw.
    try:
        subprocess.run(["nmcli", "connection", "delete", "id", ssid],
                       capture_output=True, text=True, timeout=10)
    except Exception:
        pass
    args = ["device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    try:
        r = _run(args, timeout=timeout)
        lines = [ln for ln in (r.stdout + r.stderr).strip().splitlines() if ln.strip()]
        msg = lines[-1] if lines else ("Connected" if r.returncode == 0 else "Failed")
        return r.returncode == 0, msg
    except subprocess.TimeoutExpired:
        return False, "Timed out"
    except Exception as exc:
        return False, str(exc)


def current_ssid() -> str | None:
    try:
        out = _run(["-t", "-f", "ACTIVE,SSID", "device", "wifi"], timeout=8).stdout
        for line in out.splitlines():
            if line.startswith("yes:"):
                return line.split(":", 1)[1]
    except Exception:
        pass
    return None


def disconnect() -> str | None:
    ssid = current_ssid()
    if ssid:
        try:
            _run(["connection", "down", "id", ssid], timeout=15)
        except Exception:
            pass
    return ssid
