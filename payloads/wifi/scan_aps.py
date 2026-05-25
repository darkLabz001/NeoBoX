#!/usr/bin/env python3
# neo-name: Scan APs
# neo-desc: List nearby Wi-Fi access points
import os
os.execvp("nmcli", ["nmcli", "-c", "no", "dev", "wifi", "list"])
