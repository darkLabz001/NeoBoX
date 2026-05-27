#!/usr/bin/env python3
import eventlet
eventlet.monkey_patch()

import sys
import os
import pty
import subprocess
import select
import termios
import struct
import fcntl
import shlex
import socket
import time
import psutil
import signal
import base64
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

async_mode = 'eventlet'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'neobox-secret-2026!'
# Use a higher ping timeout for stable connection
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode, ping_timeout=60)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ROM_DIR = Path.home() / "roms" / "ps1"
PAYLOAD_DIR = BASE_DIR / "payloads"
ROM_DIR.mkdir(parents=True, exist_ok=True)

# Global state for mobile sensor sharing
mobile_data = {
    'gps': {'lat': 0, 'lon': 0, 'alt': 0, 'acc': 0},
    'last_seen': 0
}

# System Stats Helper
def get_sys_info():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    temp = 0
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = int(f.read()) / 1000.0
    except: pass
    return {
        'cpu': cpu, 'ram': ram, 'disk': disk, 'temp': temp,
        'uptime': time.time() - psutil.boot_time(),
        'load': os.getloadavg()
    }

def stats_thread():
    while True:
        try:
            info = get_sys_info()
            socketio.emit('sys_stats', info, namespace='/system')
        except: pass
        socketio.sleep(2)

def live_view_thread():
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(("127.0.0.1", 9998))
            raw_size = sock.recv(4)
            if len(raw_size) == 4:
                size = struct.unpack(">I", raw_size)[0]
                data = b""
                while len(data) < size:
                    chunk = sock.recv(min(size - len(data), 8192))
                    if not chunk: break
                    data += chunk
                if len(data) == size:
                    encoded = base64.b64encode(data).decode('utf-8')
                    socketio.emit('live_frame', {'image': encoded}, namespace='/system')
            sock.close()
        except: pass
        socketio.sleep(0.2)

socketio.start_background_task(stats_thread)
socketio.start_background_task(live_view_thread)

class TerminalSession:
    def __init__(self):
        self.fd = None
        self.child_pid = None

    def kill_existing(self):
        if self.child_pid:
            try:
                os.kill(self.child_pid, signal.SIGKILL)
                os.waitpid(self.child_pid, 0)
            except: pass
        self.child_pid = None
        self.fd = None

    def spawn(self):
        self.kill_existing()
        try:
            (self.child_pid, self.fd) = pty.fork()
            if self.child_pid == 0:
                os.environ["TERM"] = "xterm-256color"
                os.environ["SHELL"] = "/bin/bash"
                os.environ["HOME"] = str(Path.home())
                os.chdir(str(BASE_DIR))
                os.execvp("/bin/bash", ["/bin/bash", "-i"])
            else:
                socketio.start_background_task(target=self.read_output)
        except: pass

    def read_output(self):
        while self.fd:
            socketio.sleep(0.01)
            if self.fd:
                r, w, e = select.select([self.fd], [], [], 0)
                if self.fd in r:
                    try:
                        output = os.read(self.fd, 10240).decode(errors='replace')
                        socketio.emit("terminal_output", {"data": output}, namespace="/terminal")
                    except: break
        self.fd = None

    def write_input(self, data):
        if self.fd: os.write(self.fd, data.encode())

    def resize(self, rows, cols):
        if self.fd:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)

term = TerminalSession()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/mobile')
def mobile_link(): return render_template('mobile.html')

@app.route('/api/stats')
def api_stats(): return jsonify(get_sys_info())

@app.route('/api/gps')
def get_mobile_gps(): return jsonify(mobile_data)

@app.route('/api/wigle', methods=['GET', 'POST'])
def handle_wigle_config():
    path = BASE_DIR / "config" / "wigle.json"
    if request.method == 'POST':
        data = request.get_json(force=True)
        with open(path, 'w') as f:
            json.dump(data, f)
        return jsonify({"success": True})
    if path.exists():
        with open(path, 'r') as f:
            try: return jsonify(json.load(f))
            except: pass
    return jsonify({"api_name": "", "api_key": ""})

@app.route('/api/wigle/upload', methods=['POST'])
def upload_to_wigle():
    cfg_path = BASE_DIR / "config" / "wigle.json"
    if not cfg_path.exists(): return jsonify({"error": "No config"}), 400
    with open(cfg_path, 'r') as f: cfg = json.load(f)
    target_dir = Path.home() / "neo" / "loot" / "wardrive"
    files = list(target_dir.glob("*.csv"))
    if not files: return jsonify({"error": "No files"}), 404
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    import requests
    from requests.auth import HTTPBasicAuth
    try:
        with open(files[0], 'rb') as f:
            r = requests.post("https://api.wigle.net/api/v2/file/upload",
                            auth=HTTPBasicAuth(cfg["api_name"], cfg["api_key"]),
                            files={'file': f}, timeout=30)
        return jsonify({"success": True, "details": r.json()})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/files')
def list_files():
    section = request.args.get('section', 'roms')
    target = ROM_DIR if section == 'roms' else PAYLOAD_DIR
    files = []
    if target.exists():
        for f in sorted(target.glob("**/*")):
            if f.is_file() and not f.name.startswith("."):
                files.append({"name": f.name, "path": str(f.relative_to(target.parent)), "size": f.stat().st_size, "mtime": f.stat().st_mtime})
    return jsonify(files)

@app.route('/api/delete', methods=['POST'])
def delete_file():
    path = request.json.get('path')
    abs_path = (ROM_DIR.parent / path).resolve()
    if abs_path.exists():
        abs_path.unlink()
        return jsonify({"success": True})
    return jsonify({"error": "Not found"}), 404

@app.route('/api/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    target_type = request.form.get('type', 'rom')
    save_path = PAYLOAD_DIR / "custom" / file.filename if target_type == 'payload' else ROM_DIR / file.filename
    save_path.parent.mkdir(parents=True, exist_ok=True)
    file.save(str(save_path))
    return jsonify({"success": True})

@socketio.on("connect", namespace="/terminal")
def connect_term(): term.spawn()
@socketio.on("terminal_input", namespace="/terminal")
def terminal_input(data): term.write_input(data["data"])
@socketio.on("remote_action", namespace="/remote")
def remote_action(data):
    action = data.get("action")
    if action:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(action.encode(), ("127.0.0.1", 9999))
        sock.close()

@socketio.on('gps_update', namespace='/system')
def handle_gps(data):
    global mobile_data
    mobile_data['gps'] = data
    mobile_data['last_seen'] = time.time()
    socketio.emit('mobile_gps_broadcast', data, namespace='/system')

if __name__ == '__main__':
    # Fallback to pure HTTP on 8888 for the main UI.
    # Mobile users can manually switch to HTTPS if they need GPS perms.
    # To avoid eventlet SSL errors, we run only ONE protocol per port.
    print("--- NeoBox Web UI: Starting on port 8888 ---")
    socketio.run(app, host='0.0.0.0', port=8888, debug=False)
