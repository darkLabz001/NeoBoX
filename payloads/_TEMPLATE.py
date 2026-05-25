#!/usr/bin/env python3
# NeoBoX payload template — copy into a section folder, e.g. payloads/recon/, and rename.
# The UI reads these header comments (no code is run to read them):
# neo-name: My Payload          # shown on the tile
# neo-desc: what it does         # optional
# neo-needs: target              # optional; UI prompts for each via the on-screen keyboard
# neo-icon: recon                # optional; an icon name from assets/icons (else a glyph badge)
import os, sys

# Collected inputs arrive both as argv (in order) and as NEO_<NAME> env vars (uppercased).
target = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NEO_TARGET", "")).strip()

print(f"payload running. target={target!r}")
# To run a tool with live streaming output, replace this process with it:
# os.execvp("nmap", ["nmap", "-sV", target])
