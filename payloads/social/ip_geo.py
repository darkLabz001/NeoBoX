#!/usr/bin/env python3
# neo-name: IP Geolocate
# neo-desc: Look up geolocation for an IP/host
# neo-needs: target
import os, sys, json, urllib.request
t = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NEO_TARGET", "")).strip()
if not t: sys.exit("No target given.")
try:
    d = json.load(urllib.request.urlopen(f"http://ip-api.com/json/{t}", timeout=6))
    for k in ("query", "country", "regionName", "city", "isp", "org", "lat", "lon"):
        print(f"{k:>10}: {d.get(k,'')}")
except Exception as e:
    print("lookup failed:", e)
