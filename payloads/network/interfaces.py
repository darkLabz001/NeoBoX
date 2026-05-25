#!/usr/bin/env python3
# neo-name: Interfaces
# neo-desc: Show network interfaces and addresses
import os
os.execvp("ip", ["ip", "-c", "addr"])
