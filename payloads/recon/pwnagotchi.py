#!/usr/bin/env python3
# neo-name: Pwnagotchi
# neo-desc: WPA handshake/PMKID harvester (USB monitor adapter)
# neo-icon: recon
# neo-screen: pwnagotchi
# neo-apt: hcxdumptool, hcxtools
# neo-input: gpio
"""Pwnagotchi-style WiFi handshake harvester. Opens a custom NeoBoX screen
(neo/screens/pwnagotchi.py) that runs hcxdumptool on the USB monitor-mode
adapter and collects WPA PMKIDs/handshakes into ~/loot — without taking the
device over. Only use against networks you own or are authorized to test."""
import sys

sys.exit("Open Pwnagotchi from the NeoBoX Recon menu (it uses a custom UI screen).")
