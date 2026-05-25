"""WiFi control via nmcli (scan / connect / disconnect)."""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "wifi.log"


def _log(msg: str):
    try:
        with open(LOG, "a") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


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
    """Switch to `ssid`, leaving any current network. Returns (ok, message).

    Switching reliably needs three things, or NetworkManager silently keeps you
    on the original network:
      1. Tear down the current connection with `connection down` first. A manual
         down tells NM not to auto-reconnect that profile, so it can't win the
         race back onto the old network while the new one is associating.
      2. Delete any stale saved profile for the target SSID, so a wrong saved
         password isn't reused (fails even when the typed password is correct).
      3. Verify we actually landed on `ssid` afterwards — nmcli can report
         success yet leave us on a previously-saved autoconnect network.
    """
    cur = current_ssid()
    if cur and cur != ssid:
        _log(f"switch: bringing down current network '{cur}' before connecting '{ssid}'")
        try:
            _run(["connection", "down", "id", cur], timeout=15)
        except Exception as exc:
            _log(f"  (down failed, continuing: {exc})")
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
        _log(f"connect '{ssid}': rc={r.returncode} out={lines}")
    except subprocess.TimeoutExpired:
        _log(f"connect '{ssid}': timed out after {timeout}s")
        return False, "Timed out"
    except Exception as exc:
        _log(f"connect '{ssid}': error {exc}")
        return False, str(exc)
    # Verify the switch actually took — don't trust the return code alone.
    actual = current_ssid()
    if actual == ssid:
        return True, f"Connected to {ssid}"
    _log(f"connect '{ssid}': NOT active afterwards (now on '{actual}')")
    if actual:
        return False, f"Failed — still on {actual}"
    return False, msg


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
