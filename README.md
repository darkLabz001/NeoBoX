# Neo

A custom pentesting firmware UI for the Raspberry Pi 3B+ + Waveshare Game HAT
(3.5" 480×320 IPS, joystick + A/B/X/Y + Start/Select + L/R + Menu/Exit, dual
speakers). Boots straight into a themeable, controller-driven launcher for
security tools.

## Layout
```
run.py                 entry point (windowed dev / fullscreen device / screenshot)
neo/
  app.py               window, scaling, screen stack, input routing, main loop
  config.py            paths + 480x320 logical screen
  inputs.py            logical actions; keyboard (dev) + GPIO (device) backends
  theme.py             theme loading (themes/*.json)
  assets.py            icon rendering (PNG or procedural glyph badge)
  ui/statusbar.py      top bar (title, wifi, clock)
  ui/grid.py           scrollable paginated icon grid
  screens/             home (categories), category (tools), console
themes/                midnight, synthwave, …
config/tools.json      tool catalog (categories -> tools)
config/buttons.json    GPIO pin map (verify with tools/button_mapper.py)
tools/button_mapper.py interactive GPIO->button mapper (run on the Pi)
scripts/sync.sh        rsync to the Pi
```

## Dev
```
python3 run.py                          # 2x window on HDMI
python3 run.py --theme synthwave
python3 run.py --screenshot out.png --actions RIGHT,A   # offscreen preview
```

## On the Game HAT
```
python3 run.py --mode fullscreen --gpio
```

## Controls (dev keyboard)
Arrows/WASD = D-pad · J/Enter = A · K/Esc = B · U = X · I = Y ·
Q = L · E = R · 1 = Select · 2 = Start · M = Menu · Backspace = Exit
