#!/usr/bin/env python3
# neo-name: Hash ID
# neo-desc: Identify a hash type
# neo-needs: hash
import os, sys, shutil
h = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NEO_HASH", "")).strip()
if not h: sys.exit("No hash given.")
tool = "hashid" if shutil.which("hashid") else ("hash-identifier" if shutil.which("hash-identifier") else None)
if not tool: sys.exit("hashid not installed.")
os.execvp(tool, [tool, h])
