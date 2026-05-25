#!/usr/bin/env python3
# neo-name: Nmap Full
# neo-desc: Aggressive all-ports scan
# neo-needs: target
import os, sys, shutil
t = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NEO_TARGET", "")).strip()
if not t: sys.exit("No target given.")
if not shutil.which("nmap"): sys.exit("nmap not installed.")
os.execvp("sudo", ["sudo", "-n", "nmap", "-A", "-p-", t])
