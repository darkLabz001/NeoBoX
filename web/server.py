#!/usr/bin/env python3
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

app = Flask(__name__)
app.config['SECRET_KEY'] = 'neobox-secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

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
        
        (self.child_pid, self.fd) = pty.fork()
        if self.child_pid == 0:
            # Child process
            os.environ["TERM"] = "xterm-256color"
            os.environ["SHELL"] = "/bin/bash"
            os.chdir(str(BASE_DIR))
            os.execvp("/bin/bash", ["/bin/bash"])
        else:
            # Parent process
            socketio.start_background_task(target=self.read_output)

    def read_output(self):
        max_read_bytes = 1024 * 20
        while self.fd:
            socketio.sleep(0.01)
            if self.fd:
                timeout_sec = 0
                r, w, e = select.select([self.fd], [], [], timeout_sec)
                if self.fd in r:
                    output = os.read(self.fd, max_read_bytes).decode(errors='replace')
                    socketio.emit("terminal_output", {"data": output}, namespace="/terminal")

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
    filename = shlex.quote(file.filename).strip("'") # basic sanitization
    
    if target_type == 'payload':
        # payloads need to go into a specific section
        section = request.form.get('section', 'custom')
        save_path = PAYLOAD_DIR / section / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        save_path = ROM_DIR / filename

    file.save(str(save_path))
    if target_type == 'payload':
        save_path.chmod(0o755) # make payloads executable

    return jsonify({"success": True, "path": str(save_path)})

@socketio.on("connect", namespace="/terminal")
def connect():
    term.spawn()
    print("Terminal client connected")

@socketio.on("terminal_input", namespace="/terminal")
def terminal_input(data):
    term.write_input(data["data"])

@socketio.on("terminal_resize", namespace="/terminal")
def terminal_resize(data):
    term.resize(data["rows"], data["cols"])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
