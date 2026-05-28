#!/usr/bin/env python3
# neo-name: Flock Finder
# neo-desc: Locate Flock / ALPR surveillance cameras (OSM data)
# neo-icon: recon
# neo-screen: flock
# neo-input: gpio
"""Flock Finder — find public-surveillance ALPR cameras (Flock Safety and
similar automated license-plate readers) near a location, using the community-
maintained tags in OpenStreetMap (the same dataset DeFlock and the EFF Atlas
of Surveillance build on).

Pure transparency tool. Use it to know what's deployed in your neighborhood;
do not use it to interfere with the cameras themselves. All cameras shown are
publicly-mapped fixed installations on public infrastructure.

The custom screen lives at neo/screens/flock.py; this file is the discovery
stub plus a --list mode that returns cameras as JSON for any other tool that
wants to consume them."""
import os
import sys
import json
import urllib.parse
import urllib.request

OVERPASS_HOSTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


def query(lat: float, lon: float, radius_m: int = 20000) -> list[dict]:
    q = (
        "[out:json][timeout:25];"
        "("
        f'nwr["man_made"="surveillance"]["surveillance:type"="ALPR"](around:{radius_m},{lat},{lon});'
        f'nwr["man_made"="surveillance"]["camera:type"="ALPR"](around:{radius_m},{lat},{lon});'
        f'nwr["operator"~"Flock",i](around:{radius_m},{lat},{lon});'
        ");"
        "out center 80;"
    )
    body = urllib.parse.urlencode({"data": q}).encode()
    last_err = None
    for url in OVERPASS_HOSTS:
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"User-Agent": "NeoBoX-Recon/0.1"})
            with urllib.request.urlopen(req, timeout=28) as r:
                return json.load(r).get("elements", [])
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"all Overpass mirrors failed: {last_err}")


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--list":
        lat, lon = float(sys.argv[2]), float(sys.argv[3])
        radius = int(sys.argv[4]) if len(sys.argv) > 4 else 20000
        try:
            es = query(lat, lon, radius)
        except Exception as exc:
            print(json.dumps({"error": str(exc)}))
            return
        out = []
        for e in es:
            la = e.get("lat") or e.get("center", {}).get("lat")
            lo = e.get("lon") or e.get("center", {}).get("lon")
            if la is None or lo is None:
                continue
            t = e.get("tags", {})
            out.append({
                "lat": la, "lon": lo, "osm_id": e["id"], "osm_type": e["type"],
                "operator": t.get("operator", ""),
                "name": (t.get("name") or t.get("description") or t.get("ref") or ""),
                "type": (t.get("surveillance:type") or t.get("camera:type") or ""),
                "direction": t.get("camera:direction") or t.get("direction") or "",
            })
        print(json.dumps(out))
        return
    sys.exit("Open Flock Finder from the NeoBoX Recon menu (custom UI screen).")


if __name__ == "__main__":
    main()
