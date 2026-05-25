#!/usr/bin/env python3
# neo-name: WhatWeb
# neo-desc: Fingerprint a web target
# neo-needs: url
import os, sys, shutil
u = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NEO_URL", "")).strip()
if not u: sys.exit("No URL given.")
if not shutil.which("whatweb"): sys.exit("whatweb not installed.")
os.execvp("whatweb", ["whatweb", u])
