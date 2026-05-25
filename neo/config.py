"""Global configuration and paths for the Neo firmware UI."""
from pathlib import Path

# Project layout ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
THEMES_DIR = BASE_DIR / "themes"
CONFIG_DIR = BASE_DIR / "config"
ASSETS_DIR = BASE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
BACKGROUNDS_DIR = ASSETS_DIR / "backgrounds"
PAYLOADS_DIR = BASE_DIR / "payloads"

# Logical screen: native resolution of the Waveshare Game HAT 3.5" IPS.
# We always render to a 480x320 surface and scale it to the real window.
SCREEN_W = 480
SCREEN_H = 320
FPS = 30

DEFAULT_THEME = "neobox"

# Files
SECTIONS_FILE = CONFIG_DIR / "sections.json"
BUTTONS_FILE = CONFIG_DIR / "buttons.json"
