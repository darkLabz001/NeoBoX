#!/usr/bin/env python3
# neo-name: Routes
# neo-desc: Show the routing table
import os
os.execvp("ip", ["ip", "-c", "route"])
