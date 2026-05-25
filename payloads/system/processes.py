#!/usr/bin/env python3
# neo-name: Processes
# neo-desc: Top processes by CPU
import os
os.system("top -b -n1 | head -25")
