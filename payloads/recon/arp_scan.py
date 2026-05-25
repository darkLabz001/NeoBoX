#!/usr/bin/env python3
# neo-name: ARP Scan
# neo-desc: Discover hosts on the local network
import os, shutil
if shutil.which("arp-scan"):
    os.execvp("sudo", ["sudo", "-n", "arp-scan", "--localnet"])
os.execvp("ip", ["ip", "neigh"])
