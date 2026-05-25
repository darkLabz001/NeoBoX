"""Animated boot intro — Arasaka-style red/black glitch with terminal boot log,
a glitchy NEOBOX logo reveal, and the bootup track. Skippable with any button.
"""
from __future__ import annotations

import random

import pygame

from . import Screen
from .. import config

W, H = config.SCREEN_W, config.SCREEN_H

RED = (255, 42, 48)
DRED = (130, 12, 18)
WHITE = (236, 240, 255)
CYAN = (45, 226, 255)
BG = (6, 4, 6)

BOOT_LINES = [
    "> SECURE ENCLAVE ........ UNLOCKED",
    "> KERNEL MODULES ........ LOADED",
    "> RADIO STACK ........... ONLINE",
    "> PAYLOAD VAULT ......... MOUNTED",
    "> NEURAL UPLINK ......... SYNCED",
    "> NEOBOX CORE ........... READY",
]

T_LOG = 0.8       # boot log starts
T_LINE = 0.42     # per line
T_LOGO = 4.0      # logo reveal
T_TAG = 6.2       # tagline
T_FLASH = 8.4
T_END = 9.4


class IntroScreen(Screen):
    modal = True
    hide_hints = True

    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        self.done = False
        self._scanlines = self._make_scanlines()
        self._mono = self._font(13)
        self._mono_sm = self._font(10)
        self._logo = self._font(46, bold=True)
        self._tag = self._font(12)
        self._play_music()

    # --- setup ----------------------------------------------------------
    def _font(self, size, bold=False):
        path = pygame.font.match_font("dejavusansmono", bold=bold) \
            or pygame.font.get_default_font()
        return pygame.font.Font(path, size)

    def _make_scanlines(self):
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(0, H, 3):
            pygame.draw.line(s, (0, 0, 0, 70), (0, y), (W, y))
        return s

    def _play_music(self):
        try:
            if not pygame.mixer.get_init():
                return
            for ext in ("ogg", "mp3"):
                p = config.ASSETS_DIR / "sounds" / f"bootup.{ext}"
                if p.exists():
                    pygame.mixer.music.load(str(p))
                    pygame.mixer.music.set_volume(0.8)
                    pygame.mixer.music.play()
                    return
        except Exception as exc:
            print(f"[intro] music failed: {exc}")

    # --- lifecycle ------------------------------------------------------
    def on_action(self, action: str):
        self._finish()

    def update(self, dt: float):
        self.t += dt
        if self.t >= T_END:
            self._finish()

    def _finish(self):
        if self.done:
            return
        self.done = True
        try:
            pygame.mixer.music.fadeout(1200)
        except Exception:
            pass
        self.app.go_home()

    # --- helpers --------------------------------------------------------
    def _glitch(self, surf, intensity):
        for _ in range(int(intensity * 5)):
            y = random.randint(0, H - 6)
            h = random.randint(2, 9)
            off = random.randint(-14, 14)
            try:
                sub = surf.subsurface(pygame.Rect(0, y, W, min(h, H - y))).copy()
                surf.blit(sub, (off, y))
            except ValueError:
                pass
        if random.random() < intensity * 0.5:   # red bar flicker
            y = random.randint(0, H - 4)
            pygame.draw.rect(surf, DRED, (0, y, W, random.randint(1, 3)))

    def _chroma_text(self, surf, font, text, center, base=RED):
        r = font.render(text, True, (255, 60, 60))
        c = font.render(text, True, CYAN)
        w = font.render(text, True, WHITE)
        rect = w.get_rect(center=center)
        j = random.randint(-2, 2)
        surf.blit(r, rect.move(-2 + j, 0))
        surf.blit(c, rect.move(2 - j, 0))
        surf.blit(w, rect)

    # --- draw -----------------------------------------------------------
    def draw(self, surf, theme):
        t = self.t
        surf.fill(BG)

        # opening sweep
        if t < 1.0:
            sweep_y = int((t / 1.0) * H)
            pygame.draw.rect(surf, DRED, (0, 0, W, sweep_y))
            pygame.draw.line(surf, RED, (0, sweep_y), (W, sweep_y), 2)

        # terminal boot log (fades out as the logo reveals)
        if T_LOG <= t < T_LOGO + 0.8:
            log = pygame.Surface((W, H), pygame.SRCALPHA)
            y = 40
            shown = int((t - T_LOG) / T_LINE)
            for i, line in enumerate(BOOT_LINES[:shown + 1]):
                color = WHITE if i < shown else RED
                txt = line + (" _" if (i == shown and int(t * 2) % 2 == 0) else "")
                log.blit(self._mono.render(txt, True, color), (26, y))
                y += 22
            if t > T_LOGO:
                log.set_alpha(int(255 * max(0.0, 1 - (t - T_LOGO) / 0.8)))
            surf.blit(log, (0, 0))

        # HUD frame corners (corporate)
        if t >= 0.3:
            self._corners(surf)

        # logo reveal
        if t >= T_LOGO:
            self._chroma_text(surf, self._logo, "NEOBOX", (W // 2, H // 2 - 6))
            # underline bar grows
            p = min(1.0, (t - T_LOGO) / 1.2)
            bw = int(220 * p)
            pygame.draw.rect(surf, RED, (W // 2 - bw // 2, H // 2 + 28, bw, 3))

        # tagline
        if t >= T_TAG:
            a = min(1.0, (t - T_TAG) / 0.8)
            col = tuple(int(c * a) for c in WHITE)
            tag = self._tag.render("C O N T R O L   ·   A N A L Y Z E   ·   D O M I N A T E",
                                   True, col)
            surf.blit(tag, tag.get_rect(center=(W // 2, H // 2 + 52)))

        # scanlines overlay
        surf.blit(self._scanlines, (0, 0))

        # glitch intensity peaks at logo reveal and flash
        gi = 0.0
        if T_LOGO - 0.3 <= t < T_LOGO + 0.6:
            gi = 0.9
        elif T_LOG <= t < T_LOGO:
            gi = 0.15
        elif t >= T_FLASH:
            gi = 1.0
        if gi:
            self._glitch(surf, gi)

        # end flash
        if t >= T_FLASH:
            a = int(255 * min(1.0, (t - T_FLASH) / (T_END - T_FLASH)))
            flash = pygame.Surface((W, H))
            flash.fill(RED)
            flash.set_alpha(a)
            surf.blit(flash, (0, 0))

    def _corners(self, surf):
        c = DRED
        L = 22
        for (x, y, dx, dy) in [(6, 6, 1, 1), (W - 6, 6, -1, 1),
                               (6, H - 6, 1, -1), (W - 6, H - 6, -1, -1)]:
            pygame.draw.line(surf, c, (x, y), (x + dx * L, y), 2)
            pygame.draw.line(surf, c, (x, y), (x, y + dy * L), 2)

    def hints(self):
        return [("any", "skip")]
