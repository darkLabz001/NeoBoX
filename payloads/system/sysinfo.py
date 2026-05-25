#!/usr/bin/env python3
# neo-name: System Info
# neo-desc: Kernel, uptime, memory
import os
os.system("uname -a; echo; uptime; echo; free -h")
