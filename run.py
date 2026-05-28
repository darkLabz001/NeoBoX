#!/usr/bin/env python3
"""Entry point for the Neo firmware UI.

Examples:
  python3 run.py                         # windowed dev preview (2x) on HDMI
  python3 run.py --mode fullscreen --gpio  # on the Game HAT
  python3 run.py --screenshot out.png --actions RIGHT,RIGHT,A   # offscreen render
"""
import argparse
import os


def main():
    p = argparse.ArgumentParser(description="Neo pentesting firmware UI")
    p.add_argument("--mode", choices=["windowed", "fullscreen", "headless"], default="windowed")
    p.add_argument("--scale", type=int, default=2)
    p.add_argument("--theme", default=None)
    p.add_argument("--gpio", action="store_true", help="read Game HAT buttons via GPIO")
    p.add_argument("--screenshot", metavar="PATH", help="render one frame to PNG and exit")
    p.add_argument("--actions", default="",
                   help="comma-separated actions dispatched before the screenshot")
    p.add_argument("--settle", type=int, default=12,
                   help="frames to render before saving (lets async output arrive)")
    p.add_argument("--no-intro", action="store_true", help="skip the boot intro")
    p.add_argument("--intro", action="store_true", help="show intro (preview in screenshot)")
    args = p.parse_args()

    if args.screenshot:
        args.mode = "headless"
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    import pygame
    print("[DEBUG] pygame init...")
    pygame.init()
    print("[DEBUG] pygame font init...")
    pygame.font.init()

    from neo.app import App
    from neo.screens.home import HomeScreen

    kwargs = {"theme_name": args.theme} if args.theme else {}
    print("[DEBUG] App instance creation...")
    app = App(mode=args.mode, scale=args.scale, use_gpio=args.gpio, **kwargs)
    print("[DEBUG] App instance created.")
    # Skip the intro on an in-place restart (OTA `os.execv`, dev relaunch, etc.)
    # so you land at home instantly; only show it on a cold boot.
    def _kernel_uptime():
        try:
            with open("/proc/uptime") as fh: return float(fh.read().split()[0])
        except Exception: return 0.0
    cold_boot = _kernel_uptime() < 60

    if args.intro or (not args.screenshot and not args.no_intro and cold_boot):
        from neo.screens.intro import IntroScreen
        app.push(IntroScreen(app))
    else:
        app.push(HomeScreen(app))

    if args.screenshot:
        acts = [a.strip().upper() for a in args.actions.split(",") if a.strip()]
        app.snapshot(args.screenshot, acts, settle=args.settle)
    else:
        print("[DEBUG] app.run()...")
        app.run()


if __name__ == "__main__":
    main()
