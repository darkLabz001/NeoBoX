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
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

async_mode = 'eventlet'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'neobox-secret-2026!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ROM_DIR = Path.home() / "roms" / "ps1"
PAYLOAD_DIR = BASE_DIR / "payloads"
ROM_DIR.mkdir(parents=True, exist_ok=True)

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
        'cpu': cpu,
        'ram': ram,
        'disk': disk,
        'temp': temp,
        'uptime': time.time() - psutil.boot_time(),
        'load': os.getloadavg()
    }

# System Stats Background Task
def stats_thread():
    print("[web] background stats thread started")
    while True:
        try:
            info = get_sys_info()
            socketio.emit('sys_stats', info, namespace='/system')
        except Exception as e:
            print(f"[web] stats error: {e}")
        socketio.sleep(2)

socketio.start_background_task(stats_thread)

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
                # Child process
                os.environ["TERM"] = "xterm-256color"
                os.environ["SHELL"] = "/bin/bash"
                os.environ["HOME"] = str(Path.home())
                os.chdir(str(BASE_DIR))
                # Interactive bash with colors
                os.execvp("/bin/bash", ["/bin/bash", "-i"])
            else:
                # Parent process
                socketio.start_background_task(target=self.read_output)
                print(f"[web] terminal spawned (pid: {self.child_pid})")
        except Exception as e:
            print(f"[web] terminal spawn error: {e}")

    def read_output(self):
        max_read_bytes = 1024 * 10
        while self.fd:
            socketio.sleep(0.01)
            if self.fd:
                r, w, e = select.select([self.fd], [], [], 0)
                if self.fd in r:
                    try:
                        output = os.read(self.fd, max_read_bytes).decode(errors='replace')
                        socketio.emit("terminal_output", {"data": output}, namespace="/terminal")
                    except EOFError:
                        break
                    except Exception:
                        break
        self.fd = None
        print("[web] terminal output thread closed")

    def write_input(self, data):
        if self.fd: os.write(self.fd, data.encode())

    def resize(self, rows, cols):
        if self.fd:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)

term = TerminalSession()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/stats')
def api_stats(): return jsonify(get_sys_info())

@app.route('/api/files', methods=['GET'])
def list_files():
    section = request.args.get('section', 'roms')
    target = ROM_DIR if section == 'roms' else PAYLOAD_DIR
    files = []
    if target.exists():
        for f in sorted(target.glob("**/*")):
            if f.is_file() and not f.name.startswith("."):
                files.append({
                    "name": f.name, 
                    "path": str(f.relative_to(target.parent)), 
                    "size": f.stat().st_size,
                    "mtime": f.stat().st_mtime,
                    "type": "rom" if section == "roms" else "payload"
                })
    # Sort by newest first
    files.sort(key=lambda x: x['mtime'], reverse=True)
    return jsonify(files)

@app.route('/api/delete', methods=['POST'])
def delete_file():
    data = request.json
    path = data.get('path')
    if not path: return jsonify({"error": "No path"}), 400
    abs_path = (ROM_DIR.parent / path).resolve()
    # Security: ensure path is within ROM or Payload dirs
    if not any(str(abs_path).startswith(str(d)) for d in [ROM_DIR, PAYLOAD_DIR]):
        return jsonify({"error": "Access denied"}), 403
    if abs_path.exists():
        abs_path.unlink()
        return jsonify({"success": True})
    return jsonify({"error": "File not found"}), 404

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files: return jsonify({"error": "No file part"}), 400
        file = request.files['file']
        if file.filename == '': return jsonify({"error": "No selected file"}), 400
        target_type = request.form.get('type', 'rom')
        
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)
        
        if target_type == 'payload':
            save_path = PAYLOAD_DIR / "custom" / filename
            save_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            save_path = ROM_DIR / filename
            
        file.save(str(save_path))
        if target_type == 'payload': save_path.chmod(0o755)
        
        print(f"[web] saved {filename} to {save_path.parent}")
        return jsonify({"success": True, "path": str(save_path)})
    except Exception as e:
        print(f"[web] upload error: {e}")
        return jsonify({"error": str(e)}), 500

# SocketIO Events
@socketio.on("connect", namespace="/terminal")
def connect_term():
    print("[web] client connected to terminal")
    term.spawn()

@socketio.on("terminal_input", namespace="/terminal")
def terminal_input(data): term.write_input(data["data"])

@socketio.on("terminal_resize", namespace="/terminal")
def terminal_resize(data): term.resize(data["rows"], data["cols"])

@socketio.on("remote_action", namespace="/remote")
def remote_action(data):
    action = data.get("action")
    if action:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(action.encode(), ("127.0.0.1", 9999))
        sock.close()

if __name__ == '__main__':
    print("--- NeoBox Web UI Core 2.0 Starting ---")
    print("Binding to 0.0.0.0:8888...")
    sys.stdout.flush()
    socketio.run(app, host='0.0.0.0', port=8888, debug=False)
