#!/usr/bin/env python3
# neo-name: My IP
# neo-desc: Local and public IP addresses
import os, subprocess, urllib.request
print("Local:", subprocess.getoutput("hostname -I").strip())
try:
    print("Public:", urllib.request.urlopen("https://api.ipify.org", timeout=5).read().decode())
except Exception as e:
    print("Public: (offline)", e)
