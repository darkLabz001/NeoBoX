#!/usr/bin/env python3
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
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

# USE THREADING - No monkey patching needed
async_mode = 'threading'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'neobox-secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ROM_DIR = Path.home() / "roms" / "ps1"
PAYLOAD_DIR = BASE_DIR / "payloads"
ROM_DIR.mkdir(parents=True, exist_ok=True)

# System Stats Background Task
def stats_thread():
    while True:
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            temp = 0
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    temp = int(f.read()) / 1000.0
            except: pass
            
            socketio.emit('sys_stats', {
                'cpu': cpu,
                'ram': ram,
                'temp': temp,
                'uptime': time.time() - psutil.boot_time()
            }, namespace='/system')
        except: pass
        socketio.sleep(2)

socketio.start_background_task(stats_thread)

class TerminalSession:
    def __init__(self):
        self.fd = None
        self.child_pid = None

    def spawn(self):
        if self.child_pid: return
        try:
            (self.child_pid, self.fd) = pty.fork()
            if self.child_pid == 0:
                os.environ["TERM"] = "xterm-256color"
                os.environ["SHELL"] = "/bin/bash"
                os.chdir(str(BASE_DIR))
                os.execvp("/bin/bash", ["/bin/bash"])
            else:
                socketio.start_background_task(target=self.read_output)
        except Exception as e:
            print(f"Error spawning terminal: {e}")

    def read_output(self):
        max_read_bytes = 1024 * 20
        while self.fd:
            socketio.sleep(0.01)
            if self.fd:
                r, w, e = select.select([self.fd], [], [], 0)
                if self.fd in r:
                    try:
                        output = os.read(self.fd, max_read_bytes).decode(errors='replace')
                        socketio.emit("terminal_output", {"data": output}, namespace="/terminal")
                    except Exception: break

    def write_input(self, data):
        if self.fd: os.write(self.fd, data.encode())

    def resize(self, rows, cols):
        if self.fd:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)

term = TerminalSession()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/files', methods=['GET'])
def list_files():
    section = request.args.get('section', 'roms')
    target = ROM_DIR if section == 'roms' else PAYLOAD_DIR
    files = []
    if target.exists():
        for f in target.glob("**/*"):
            if f.is_file() and not f.name.startswith("."):
                files.append({
                    "name": f.name, 
                    "path": str(f.relative_to(target.parent)), 
                    "size": f.stat().st_size,
                    "type": "rom" if section == "roms" else "payload"
                })
    return jsonify(files)

@app.route('/api/delete', methods=['POST'])
def delete_file():
    data = request.json
    path = data.get('path')
    if not path: return jsonify({"error": "No path"}), 400
    
    # Safety check: ensure it's in roms or payloads
    abs_path = (ROM_DIR.parent / path).resolve()
    if not str(abs_path).startswith(str(ROM_DIR)) and not str(abs_path).startswith(str(PAYLOAD_DIR)):
        return jsonify({"error": "Access denied"}), 403
    
    if abs_path.exists():
        abs_path.unlink()
        return jsonify({"success": True})
    return jsonify({"error": "File not found"}), 404

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"error": "No selected file"}), 400
    target_type = request.form.get('type', 'rom')
    filename = shlex.quote(file.filename).strip("'")
    if target_type == 'payload':
        save_path = PAYLOAD_DIR / "custom" / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
    else: save_path = ROM_DIR / filename
    file.save(str(save_path))
    if target_type == 'payload': save_path.chmod(0o755)
    return jsonify({"success": True, "path": str(save_path)})

# SocketIO Events
@socketio.on("connect", namespace="/terminal")
def connect_term(): term.spawn()

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
    print("Binding to 0.0.0.0:8888...")
    sys.stdout.flush()
    socketio.run(app, host='0.0.0.0', port=8888, debug=False, allow_unsafe_werkzeug=True)
