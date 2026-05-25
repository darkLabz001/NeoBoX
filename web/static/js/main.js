const term = new Terminal({
    cursorBlink: true,
    theme: {
        background: '#06070d',
        foreground: '#eaf2ff',
        cursor: '#b14bff',
        selectionBackground: '#b14bff',
    },
    fontFamily: 'monospace',
});

const fitAddon = new FitAddon.FitAddon();
term.loadAddon(fitAddon);
term.open(document.getElementById('terminal'));
fitAddon.fit();

const socket = io('/terminal');

socket.on('connect', () => {
    console.log('Connected to terminal');
    socket.emit('terminal_resize', { cols: term.cols, rows: term.rows });
});

socket.on('terminal_output', (data) => {
    term.write(data.data);
});

term.onData((data) => {
    socket.emit('terminal_input', { data: data });
});

window.addEventListener('resize', () => {
    fitAddon.fit();
    socket.emit('terminal_resize', { cols: term.cols, rows: term.rows });
});

// Navigation
function showSection(id) {
    document.querySelectorAll('section').forEach(s => s.classList.remove('active'));
    document.getElementById(id + '-section').classList.add('active');
    if (id === 'terminal') {
        setTimeout(() => fitAddon.fit(), 100);
    } else if (id === 'files') {
        loadFiles();
    }
}

// Files
async function loadFiles() {
    const res = await fetch('/api/files?section=roms');
    const files = await res.json();
    const list = document.getElementById('rom-list');
    list.innerHTML = '';
    files.forEach(f => {
        const li = document.createElement('li');
        const size = (f.size / 1024 / 1024).toFixed(2);
        li.innerHTML = `<div>${f.name}</div><span>${size} MB</span>`;
        list.appendChild(li);
    });
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
            status.style.color = '#27e07d';
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
