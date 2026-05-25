#!/usr/bin/env python3
# neo-name: Username Lookup
# neo-desc: Search a username across sites (sherlock)
# neo-needs: username
import os, sys, shutil
u = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NEO_USERNAME", "")).strip()
if not u: sys.exit("No username given.")
if shutil.which("sherlock"):
    os.execvp("sherlock", ["sherlock", "--timeout", "10", u])
print(f"sherlock not installed. Would search for: {u}")
print("Install: pipx install sherlock-project")
