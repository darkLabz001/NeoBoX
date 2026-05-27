// Terminal Initialization
const terminalElement = document.getElementById('terminal');
const term = new Terminal({
    cursorBlink: true,
    theme: {
        background: '#000000',
        foreground: '#eaf2ff',
        cursor: '#b14bff',
        selectionBackground: 'rgba(177, 75, 255, 0.3)',
        black: '#000000',
        red: '#ff5470',
        green: '#27e07d',
        yellow: '#ffb454',
        blue: '#b14bff',
        magenta: '#ff79c6',
        cyan: '#8be9fd',
        white: '#f8f8f2',
    },
    fontFamily: '"JetBrains Mono", "Fira Code", monospace',
    fontSize: 14,
    allowProposedApi: true
});

const fitAddon = new FitAddon.FitAddon();
const webLinksAddon = new WebLinksAddon.WebLinksAddon();
term.loadAddon(fitAddon);
term.loadAddon(webLinksAddon);
term.open(terminalElement);

// Sockets
const termSocket = io('/terminal');
const sysSocket = io('/system');
const remoteSocket = io('/remote');

// Terminal logic
termSocket.on('connect', () => {
    console.log('[term] connected');
    setTimeout(() => {
        fitAddon.fit();
        termSocket.emit('terminal_resize', { cols: term.cols, rows: term.rows });
    }, 200);
});

termSocket.on('terminal_output', (data) => term.write(data.data));
term.onData((data) => termSocket.emit('terminal_input', { data: data }));

function reconnectTerminal() {
    term.reset();
    termSocket.disconnect();
    termSocket.connect();
}

// System Stats
sysSocket.on('sys_stats', (data) => {
    // Mini stats
    if(document.getElementById('cpu-mini')) document.getElementById('cpu-mini').innerText = Math.round(data.cpu) + '%';
    if(document.getElementById('temp-mini')) document.getElementById('temp-mini').innerText = Math.round(data.temp) + '°C';
    
    const up_m = Math.floor(data.uptime / 60);
    const up_h = Math.floor(up_m / 60);
    if(document.getElementById('uptime-mini')) document.getElementById('uptime-mini').innerText = `${up_h}:${(up_m % 60).toString().padStart(2, '0')}`;

    // Dashboard cards
    updateGauge('cpu', data.cpu);
    updateGauge('ram', data.ram);
    updateGauge('disk', data.disk);
    
    if(document.getElementById('temp-val')) document.getElementById('temp-val').innerText = data.temp.toFixed(1);
    if(document.getElementById('load-val')) document.getElementById('load-val').innerText = data.load.map(l => l.toFixed(2)).join(', ');
    
    const h = Math.floor(data.uptime / 3600);
    const m = Math.floor((data.uptime % 3600) / 60);
    const s = Math.floor(data.uptime % 60);
    if(document.getElementById('uptime-val')) document.getElementById('uptime-val').innerText = `${h}h ${m}m ${s}s`;
});

// Live View
sysSocket.on('live_frame', (data) => {
    const screen = document.getElementById('live-screen');
    const status = document.getElementById('live-status');
    if (screen) {
        screen.src = 'data:image/jpeg;base64,' + data.image;
        if (status) {
            status.innerText = 'LIVE';
            status.className = 'badge success';
        }
    }
});

function updateGauge(id, val) {
    const bar = document.getElementById(id + '-bar');
    const text = document.getElementById(id + '-val');
    if (bar) bar.style.width = val + '%';
    if (text) text.innerText = Math.round(val) + '%';
    
    if (val > 85) bar.style.background = '#ff5470';
    else if (val > 60) bar.style.background = '#ffb454';
    else bar.style.background = '';
}

// Navigation
function showSection(id) {
    document.querySelectorAll('section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
    
    document.getElementById(id + '-section').classList.add('active');
    document.getElementById('nav-' + id).classList.add('active');

    if (id === 'terminal') {
        setTimeout(() => {
            fitAddon.fit();
            term.focus();
        }, 100);
    } else if (id === 'files') {
        loadFiles();
    }
}

// Remote Actions
function sendAction(action) {
    remoteSocket.emit('remote_action', { action: action });
    const btn = document.getElementById('btn-' + action);
    if (btn) {
        btn.classList.add('active');
        setTimeout(() => btn.classList.remove('active'), 100);
    }
}

// Keyboard shortcuts for remote
window.addEventListener('keydown', (e) => {
    if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'SELECT' || document.activeElement.id === 'terminal') return;
    const map = {
        'ArrowUp': 'UP', 'ArrowDown': 'DOWN', 'ArrowLeft': 'LEFT', 'ArrowRight': 'RIGHT',
        'Enter': 'A', 'Escape': 'B', 'x': 'X', 'y': 'Y', 's': 'START', 'a': 'SELECT', 'q': 'L', 'e': 'R'
    };
    if (map[e.key]) {
        e.preventDefault();
        sendAction(map[e.key]);
    }
});

// File Management
let currentFileSection = 'roms';
async function loadFiles(section) {
    currentFileSection = section || currentFileSection;
    document.getElementById('tab-roms').classList.toggle('active', currentFileSection === 'roms');
    document.getElementById('tab-payloads').classList.toggle('active', currentFileSection === 'payloads');

    const list = document.getElementById('file-list');
    list.innerHTML = '<li style="justify-content: center; color: var(--text-dim)">Loading files...</li>';

    try {
        const res = await fetch(`/api/files?section=${currentFileSection}`);
        const files = await res.json();
        list.innerHTML = '';
        if (files.length === 0) {
            list.innerHTML = '<li style="justify-content: center; color: var(--text-dim)">No files found</li>';
            return;
        }
        files.forEach(f => {
            const li = document.createElement('li');
            const size = (f.size / 1024 / 1024).toFixed(2);
            li.innerHTML = `
                <div class="file-name" title="${f.name}">${f.name}</div>
                <div class="file-size">${size} MB</div>
                <div style="text-align: right">
                    <button class="btn-delete" onclick="deleteFile('${f.path}')" title="Delete">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            `;
            list.appendChild(li);
        });
    } catch (err) {
        list.innerHTML = '<li style="justify-content: center; color: #ff5470">Failed to load files</li>';
    }
}

async function deleteFile(path) {
    if (!confirm(`Delete ${path.split('/').pop()}?`)) return;
    try {
        const res = await fetch('/api/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        });
        if (res.ok) {
            showToast('File deleted', 'success');
            loadFiles();
        } else {
            showToast('Delete failed', 'danger');
        }
    } catch (err) {
        showToast('Error connecting to server', 'danger');
    }
}

// Upload Handling
const fileInput = document.getElementById('file-input');
const fileInfo = document.getElementById('file-info');
const dropZone = document.getElementById('drop-zone');
if(dropZone) dropZone.onclick = () => fileInput.click();

function updateFileInfo() {
    if (fileInput.files.length) {
        const file = fileInput.files[0];
        fileInfo.innerHTML = `<div class="card" style="padding: 10px; font-size: 0.8rem; background: rgba(255,255,255,0.05)"><strong>Ready:</strong> ${file.name}</div>`;
    }
}
if(fileInput) fileInput.onchange = updateFileInfo;

document.getElementById('upload-form').onsubmit = async (e) => {
    e.preventDefault();
    if (!fileInput.files.length) {
        showToast('Please select a file', 'warning');
        return;
    }
    const status = document.getElementById('upload-status');
    const btn = e.target.querySelector('button');
    status.innerHTML = 'Uploading...';
    const formData = new FormData(e.target);
    try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        if (res.ok) {
            showToast('Upload successful!', 'success');
            status.innerHTML = '';
            fileInfo.innerHTML = '';
            fileInput.value = '';
            loadFiles();
        } else {
            showToast('Upload failed', 'danger');
        }
    } catch (err) {
        showToast('Connection error', 'danger');
    }
};

function showToast(msg, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.cssText = `background: ${type === 'success' ? '#27e07d' : type === 'danger' ? '#ff5470' : '#ff2e97'}; color: white; padding: 10px 20px; border-radius: 5px; margin-top: 10px; font-weight: bold;`;
    toast.innerText = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// Initial Load
showSection('dashboard');
loadWigleConfig();

async function loadWigleConfig() {
    try {
        const res = await fetch('/api/wigle');
        const data = await res.json();
        document.getElementById('wigle-name').value = data.api_name || '';
        document.getElementById('wigle-key').value = data.api_key || '';
    } catch (err) {}
}

async function updateWigleConfig() {
    const api_name = document.getElementById('wigle-name').value;
    const api_key = document.getElementById('wigle-key').value;
    console.log('[wigle] saving config...', { api_name });
    try {
        const res = await fetch('/api/wigle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_name, api_key })
        });
        if (res.ok) {
            showToast('WiGLE Config Saved', 'success');
        } else {
            console.error('[wigle] save failed', res.status);
            showToast('Failed to save config: ' + res.status, 'danger');
        }
    } catch (err) {
        console.error('[wigle] error', err);
        showToast('Failed to save config', 'danger');
    }
}

async function uploadWigle() {
    const status = document.getElementById('wigle-status');
    status.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Preparing WiGLE upload...';
    try {
        const res = await fetch('/api/wigle/upload', { method: 'POST' });
        const result = await res.json();
        if (result.success) {
            showToast('WiGLE Upload Successful!', 'success');
            status.innerHTML = `<span class="text-success">Success: ${result.details.id || 'Uploaded'}</span>`;
        } else {
            showToast(result.error, 'danger');
            status.innerHTML = `<span class="text-danger">${result.error}</span>`;
        }
    } catch (err) {
        showToast('Upload Error', 'danger');
        status.innerHTML = '';
    }
}
