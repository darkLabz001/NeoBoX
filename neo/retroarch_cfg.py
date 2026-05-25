"""Write settings into RetroArch's main config (~/.config/retroarch/retroarch.cfg).

We edit the main cfg directly instead of using --appendconfig, because
--appendconfig is unreliable for input/driver keys on this build. Unspecified
keys (e.g. a saved RetroAchievements login) are preserved.
"""
from __future__ import annotations

import re
from pathlib import Path

CFG = Path.home() / ".config" / "retroarch" / "retroarch.cfg"

# HAT buttons -> RetroArch. These keyboard keys match the keybridge 'retroarch'
# profile (A=x B=z X=s Y=a L=q R=w, Start=enter, Select=rshift, dpad=arrows).
BASE = {
    "input_driver": "udev",
    "video_fullscreen": "true",
    "menu_driver": "rgui",
    "menu_swap_ok_cancel": "false",
    "input_player1_up_key": "up",
    "input_player1_down_key": "down",
    "input_player1_left_key": "left",
    "input_player1_right_key": "right",
    "input_player1_a_key": "x",
    "input_player1_b_key": "z",
    "input_player1_x_key": "s",
    "input_player1_y_key": "a",
    "input_player1_l_key": "q",
    "input_player1_r_key": "w",
    "input_player1_start_key": "enter",
    "input_player1_select_key": "rshift",
    # SELECT(hotkey) + START = quit
    "input_enable_hotkey_key": "rshift",
    "input_exit_emulator_key": "enter",
    # menu also drivable by the keyboard directly
    "input_menu_toggle_key": "f1",
    # RetroAchievements available (login is entered in the menu and saved here)
    "cheevos_enable": "true",
    "cheevos_hardcore_mode_enable": "false",
}


def apply(extra: dict | None = None):
    settings = dict(BASE)
    if extra:
        settings.update(extra)
    CFG.parent.mkdir(parents=True, exist_ok=True)
    lines = CFG.read_text(errors="replace").splitlines() if CFG.exists() else []
    seen = set()
    out = []
    for line in lines:
        m = re.match(r'\s*([\w_]+)\s*=', line)
        key = m.group(1) if m else None
        if key in settings:
            out.append(f'{key} = "{settings[key]}"')
            seen.add(key)
        else:
            out.append(line)
    for k, v in settings.items():
        if k not in seen:
            out.append(f'{k} = "{v}"')
    CFG.write_text("\n".join(out) + "\n")
    return CFG
