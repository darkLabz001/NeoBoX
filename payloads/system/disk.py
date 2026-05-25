#!/usr/bin/env python3
# neo-name: Disk
# neo-desc: Filesystem usage
import os
os.execvp("df", ["df", "-h"])
