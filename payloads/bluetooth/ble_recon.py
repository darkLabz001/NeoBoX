#!/usr/bin/env python3
# neo-name: BT Recon & Auto-Connect
# neo-desc: Scan for devices and attempt pairing without credentials
# neo-icon: bluetooth

import subprocess
import time
import sys
import re

def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode()
    except subprocess.CalledProcessError as e:
        return e.output.decode()

def main():
    print("--- Bluetooth Recon & Auto-Connect ---")
    print("[*] Powering on Bluetooth...")
    run_cmd("sudo bluetoothctl power on")
    run_cmd("sudo bluetoothctl agent NoInputNoOutput")
    run_cmd("sudo bluetoothctl default-agent")
    
    print("[*] Scanning for devices (10s)...")
    scan_raw = run_cmd("hcitool scan")
    devices = []
    for line in scan_raw.splitlines():
        m = re.match(r"\s*([0-9A-F:]{17})\s+(.*)", line)
        if m:
            devices.append((m.group(1), m.group(2)))
    
    if not devices:
        print("[!] No devices found.")
        return

    print(f"[*] Found {len(devices)} device(s):")
    for mac, name in devices:
        print(f"  - {mac} ({name})")
    
    print("\n[*] Attempting Auto-Connect (Pair & Trust)...")
    for mac, name in devices:
        print(f"\n[>] Target: {name} [{mac}]")
        # Attempt to pair, trust, and connect
        # Using bluetoothctl with heredoc for automation
        script = f"""
        pair {mac}
        trust {mac}
        connect {mac}
        quit
        """
        out = subprocess.run(["bluetoothctl"], input=script.encode(), capture_output=True).stdout.decode()
        
        if "Paired: yes" in out or "Connection successful" in out:
            print(f" [+] SUCCESS: Connected to {name}")
        else:
            print(f" [-] FAILED: Could not connect to {name}")
            
    print("\n[*] Recon complete.")

if __name__ == "__main__":
    main()
