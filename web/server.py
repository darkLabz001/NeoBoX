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
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

# USE THREADING - No monkey patching needed
async_mode = 'threading'

print(f"--- NeoBox Web UI Starting (Mode: {async_mode}) ---")
sys.stdout.flush()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'neobox-secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ROM_DIR = Path.home() / "roms" / "ps1"
PAYLOAD_DIR = BASE_DIR / "payloads"

# Ensure directories exist
ROM_DIR.mkdir(parents=True, exist_ok=True)

class TerminalSession:
    def __init__(self):
        self.fd = None
        self.child_pid = None

    def spawn(self):
        if self.child_pid:
            return
        
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
                    except Exception:
                        break

    def write_input(self, data):
        if self.fd:
            os.write(self.fd, data.encode())

    def resize(self, rows, cols):
        if self.fd:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)

term = TerminalSession()

@app.route('/')
def index():
    return render_template('index.html')

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
                    "size": f.stat().st_size
                })
    return jsonify(files)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    target_type = request.form.get('type', 'rom')
    filename = shlex.quote(file.filename).strip("'")
    
    if target_type == 'payload':
        save_path = PAYLOAD_DIR / "custom" / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        save_path = ROM_DIR / filename

    file.save(str(save_path))
    if target_type == 'payload':
        save_path.chmod(0o755)

    return jsonify({"success": True, "path": str(save_path)})

@socketio.on("connect", namespace="/terminal")
def connect():
    term.spawn()

@socketio.on("terminal_input", namespace="/terminal")
def terminal_input(data):
    term.write_input(data["data"])

@socketio.on("terminal_resize", namespace="/terminal")
def terminal_resize(data):
    term.resize(data["rows"], data["cols"])

if __name__ == '__main__':
    print("Binding to 0.0.0.0:8888...")
    sys.stdout.flush()
    try:
        # allow_unsafe_werkzeug=True is needed for latest Werkzeug when using socketio
        socketio.run(app, host='0.0.0.0', port=8888, debug=False, allow_unsafe_werkzeug=True)
    except Exception as e:
        print(f"CRITICAL STARTUP ERROR: {e}")
        sys.stdout.flush()
