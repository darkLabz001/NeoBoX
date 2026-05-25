// Terminal Setup
const term = new Terminal({
    cursorBlink: true,
    theme: {
        background: '#06070d',
        foreground: '#eaf2ff',
        cursor: '#b14bff',
        selectionBackground: '#b14bff',
    },
    fontFamily: 'monospace',
    fontSize: 14
});

const fitAddon = new FitAddon.FitAddon();
term.loadAddon(fitAddon);
term.open(document.getElementById('terminal'));
fitAddon.fit();

// Sockets
const termSocket = io('/terminal');
const sysSocket = io('/system');
const remoteSocket = io('/remote');

termSocket.on('connect', () => {
    termSocket.emit('terminal_resize', { cols: term.cols, rows: term.rows });
});

termSocket.on('terminal_output', (data) => {
    term.write(data.data);
});

term.onData((data) => {
    termSocket.emit('terminal_input', { data: data });
});

// System Stats
sysSocket.on('sys_stats', (data) => {
    // Update dashboard
    document.getElementById('cpu-val').innerText = data.cpu + '%';
    document.getElementById('cpu-bar').style.width = data.cpu + '%';
    document.getElementById('ram-val').innerText = data.ram + '%';
    document.getElementById('ram-bar').style.width = data.ram + '%';
    document.getElementById('temp-val').innerText = data.temp.toFixed(1);
    
    // Mini stats in header
    document.getElementById('cpu-mini').innerText = Math.round(data.cpu) + '%';
    document.getElementById('temp-mini').innerText = Math.round(data.temp) + '°C';
    
    // Uptime
    const h = Math.floor(data.uptime / 3600);
    const m = Math.floor((data.uptime % 3600) / 60);
    const s = Math.floor(data.uptime % 60);
    document.getElementById('uptime-val').innerText = 
        `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
});

// Navigation
function showSection(id) {
    document.querySelectorAll('section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
    
    document.getElementById(id + '-section').classList.add('active');
    // Find the button that calls this and mark active
    event.currentTarget.classList.add('active');

    if (id === 'terminal') {
        setTimeout(() => fitAddon.fit(), 100);
    } else if (id === 'files') {
        loadFiles('roms');
    }
}

// Remote Control
function sendAction(action) {
    remoteSocket.emit('remote_action', { action: action });
    // Visual feedback
    const btn = document.getElementById('btn-' + action);
    if (btn) {
        btn.style.background = 'var(--accent)';
        setTimeout(() => btn.style.background = '', 100);
    }
}

// Keyboard shortcuts for remote
window.addEventListener('keydown', (e) => {
    if (document.activeElement.tagName === 'INPUT' || document.activeElement.id === 'terminal') return;
    
    const map = {
        'ArrowUp': 'UP', 'ArrowDown': 'DOWN', 'ArrowLeft': 'LEFT', 'ArrowRight': 'RIGHT',
        'Enter': 'A', 'Escape': 'B', 's': 'START', 'a': 'SELECT'
    };
    if (map[e.key]) sendAction(map[e.key]);
});

// Files
let currentSection = 'roms';
async function loadFiles(section) {
    currentSection = section || currentSection;
    document.getElementById('tab-roms').classList.toggle('active', currentSection === 'roms');
    document.getElementById('tab-payloads').classList.toggle('active', currentSection === 'payloads');

    const res = await fetch(`/api/files?section=${currentSection}`);
    const files = await res.json();
    const list = document.getElementById('file-list');
    list.innerHTML = '';
    files.forEach(f => {
        const li = document.createElement('li');
        const size = (f.size / 1024 / 1024).toFixed(2);
        li.innerHTML = `
            <div>
                <strong>${f.name}</strong><br>
                <small style="color: var(--text-dim)">${size} MB</small>
            </div>
            <button class="btn-delete" onclick="deleteFile('${f.path}')" title="Delete">
                <i class="fas fa-trash-alt"></i>
            </button>
        `;
        list.appendChild(li);
    });
}

async function deleteFile(path) {
    if (!confirm('Are you sure you want to delete this file?')) return;
    const res = await fetch('/api/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path })
    });
    if (res.ok) loadFiles();
    else alert('Delete failed');
}

// Upload
document.getElementById('upload-form').onsubmit = async (e) => {
    e.preventDefault();
    const status = document.getElementById('upload-status');
    status.innerText = 'Uploading...';
    status.style.color = 'var(--text)';

    const formData = new FormData(e.target);
    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        const result = await res.json();
        if (result.success) {
            status.innerText = 'Upload successful!';
            status.style.color = 'var(--success)';
            loadFiles();
        } else {
            status.innerText = 'Error: ' + result.error;
            status.style.color = 'var(--danger)';
        }
    } catch (err) {
        status.innerText = 'Error: Upload failed';
        status.style.color = 'var(--danger)';
    }
};

window.addEventListener('resize', () => {
    fitAddon.fit();
    termSocket.emit('terminal_resize', { cols: term.cols, rows: term.rows });
});
