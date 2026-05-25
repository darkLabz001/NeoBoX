#!/usr/bin/env python3
# neo-name: CPU Temp
# neo-desc: Raspberry Pi core temperature
import os, shutil
if shutil.which("vcgencmd"):
    os.execvp("vcgencmd", ["vcgencmd", "measure_temp"])
os.system("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null | awk '{printf \"%.1f C\\n\", $1/1000}'")
