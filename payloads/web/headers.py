#!/usr/bin/env python3
# neo-name: HTTP Headers
# neo-desc: Dump HTTP response headers
# neo-needs: url
import os, sys
u = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NEO_URL", "")).strip()
if not u: sys.exit("No URL given.")
if not u.startswith("http"): u = "http://" + u
os.execvp("curl", ["curl", "-sSIL", u])
