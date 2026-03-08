import os
import subprocess
import threading
import psutil
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

BASE_DIR = "servers"
os.makedirs(BASE_DIR, exist_ok=True)

servers = {}
logs = {}
server_passwords = {}

# ---------------- CORE LOGIC ----------------

def detect_java():
    try:
        subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT)
        return True
    except:
        return False

def get_startup(server_name):
    path = os.path.join(BASE_DIR, server_name, "server.conf")
    if not os.path.exists(path):
        default = "java -Xmx1024M -jar server.jar nogui"
        with open(path, "w") as f: f.write(default)
        return default
    with open(path, "r") as f: return f.read().strip()

def run_server(name):
    cmd = get_startup(name)
    try:
        process = subprocess.Popen(
            cmd.split(),
            cwd=os.path.join(BASE_DIR, name),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        servers[name], logs[name] = process, []
        # Non-blocking log reading
        for line in process.stdout:
            logs[name].append(line)
            if len(logs[name]) > 500: logs[name].pop(0)
    except Exception as e:
        if name in logs: logs[name].append(f"PANEL ERROR: {str(e)}\n")
    finally:
        servers.pop(name, None)

# ---------------- ROUTES ----------------

@app.route("/")
def home(): return render_template_string(HTML)

@app.route("/create_server", methods=["POST"])
def create_server():
    data = request.json
    name = data.get("name", "").strip()
    if not name or "/" in name: return "Invalid", 400
    path = os.path.join(BASE_DIR, name)
    if os.path.exists(path): return "Exists", 400
    os.makedirs(path)
    with open(os.path.join(path, "eula.txt"), "w") as f: f.write("eula=true")
    return "Created"

@app.route("/servers")
def list_servers(): return jsonify(os.listdir(BASE_DIR))

@app.route("/stats")
def stats(): return jsonify({"cpu": psutil.cpu_percent(), "ram": psutil.virtual_memory().percent})

@app.route("/files/<name>")
def list_files(name):
    path = os.path.join(BASE_DIR, name)
    files = []
    if os.path.exists(path):
        for f in os.listdir(path):
            is_dir = os.path.isdir(os.path.join(path, f))
            files.append({"name": f, "is_dir": is_dir})
    return jsonify(files)

@app.route("/read_file/<name>/<filename>")
def read_file(name, filename):
    path = os.path.join(BASE_DIR, name, filename)
    try:
        with open(path, "r", errors="ignore") as f: return f.read()
    except: return "Error reading file", 500

@app.route("/save_file/<name>/<filename>", methods=["POST"])
def save_file(name, filename):
    path = os.path.join(BASE_DIR, name, filename)
    with open(path, "w") as f: f.write(request.json.get("content"))
    return "Saved"

@app.route("/delete_file/<name>/<filename>", methods=["POST"])
def delete_file(name, filename):
    os.remove(os.path.join(BASE_DIR, name, filename))
    return "Deleted"

@app.route("/upload/<name>", methods=["POST"])
def upload(name):
    file = request.files['file']
    file.save(os.path.join(BASE_DIR, name, file.filename))
    return "Uploaded"

@app.route("/start/<name>", methods=["POST"])
def start(name):
    if not detect_java(): return "No Java Found", 500
    if name not in servers:
        if name not in logs: logs[name] = []
        logs[name].append("--- Starting Server ---\n")
        threading.Thread(target=run_server, args=(name,), daemon=True).start()
    return "Starting"

@app.route("/stop/<name>", methods=["POST"])
def stop(name):
    if name in servers:
        try:
            servers[name].stdin.write("stop\n")
            servers[name].stdin.flush()
        except: servers[name].kill()
    return "Stopping"

@app.route("/command/<name>", methods=["POST"])
def command(name):
    cmd = request.json.get("cmd")
    if name in servers:
        servers[name].stdin.write(cmd + "\n")
        servers[name].stdin.flush()
    return "Sent"

@app.route("/logs/<name>")
def get_logs(name):
    return jsonify(logs.get(name, ["Server not started yet..."]))

# ---------------- UI ----------------

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nebula Panel | Fixed Logs</title>
    <style>
        :root { --bg: #0d1117; --card: #161b22; --blue: #2188ff; --text: #c9d1d9; --danger: #f85149; --green: #2ea44f; --border: #30363d; }
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body { margin: 0; font-family: -apple-system, system-ui, sans-serif; background: var(--bg); color: var(--text); font-size: 13px; }
        
        .app-container { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh; }
        @media (max-width: 800px) { .app-container { grid-template-columns: 1fr; } }

        .sidebar { background: #010409; padding: 15px; border-right: 1px solid var(--border); }
        .nav-header { font-size: 13px; font-weight: 700; margin-bottom: 20px; display: flex; align-items: center; gap: 8px; color: #fff; }
        
        .server-item { 
            background: var(--card); padding: 8px 12px; border-radius: 6px; margin-bottom: 6px; 
            cursor: pointer; border: 1px solid var(--border); display: flex; align-items: center; gap: 10px;
        }
        .server-item.active { border-color: var(--blue); background: #1c2128; }

        .content { padding: 15px; width: 100%; display: flex; flex-direction: column; }
        .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px; }
        .stat-card { background: var(--card); padding: 12px; border-radius: 6px; border: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }

        /* FIXED 600PX CONSOLE */
        #console { 
            background: #000; height: 600px; padding: 12px; border-radius: 6px; 
            overflow-y: auto; font-family: 'Consolas', monospace; font-size: 11px; 
            border: 1px solid var(--border); margin-bottom: 10px; color: #00ff00; line-height: 1.4;
            white-space: pre-wrap; word-wrap: break-word;
        }
        
        .input-group { display: flex; gap: 6px; margin-bottom: 10px; }
        input { flex: 1; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border); background: #0d1117; color: white; outline: none; }
        
        button { 
            padding: 8px 14px; border-radius: 6px; border: 1px solid var(--border); cursor: pointer; 
            background: #21262d; color: #c9d1d9; font-weight: 500;
            display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
        }
        .btn-blue { background: var(--blue); color: white; border: none; }
        .btn-green { background: var(--green); color: white; border: none; }
        .btn-red { background: var(--danger); color: white; border: none; }

        svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; flex-shrink: 0; }

        /* File Manager & Modern Editor */
        .modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); display: none; z-index: 1000; padding: 15px; }
        .modal-content { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; width: 100%; max-width: 900px; margin: auto; height: 85vh; display: flex; flex-direction: column; overflow: hidden; }
        
        .file-list { flex: 1; overflow-y: auto; padding: 10px; }
        .file-row { display: flex; justify-content: space-between; padding: 8px 12px; background: #161b22; margin-bottom: 4px; border-radius: 6px; border: 1px solid var(--border); align-items: center; }
        
        #editor-view { display: none; flex-direction: column; height: 100%; }
        textarea { flex: 1; background: #0d1117; color: #79c0ff; padding: 15px; font-family: monospace; border: none; resize: none; outline: none; font-size: 13px; }

        .progress-wrap { width: 100%; height: 8px; background: #010409; border-radius: 10px; margin: 10px 0; display: none; overflow: hidden; }
        .progress-bar { height: 100%; background: var(--blue); width: 0%; transition: width 0.1s; }
    </style>
</head>
<body>

<div class="app-container">
    <div class="sidebar">
        <div class="nav-header">
            <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"></path></svg>
            NEBULA PANEL
        </div>
        <div id="server-container"></div>
        <div style="margin-top:20px; border-top: 1px solid var(--border); padding-top:15px;">
            <input type="text" id="new-name" placeholder="Server Name" style="width:100%; margin-bottom:8px;">
            <button class="btn-blue" onclick="createServer()" style="width:100%">Add Server</button>
        </div>
    </div>

    <div class="content">
        <div class="stats-grid">
            <div class="stat-card"><svg viewBox="0 0 24 24" style="color:var(--danger)"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg> CPU: <b id="cpu">0</b>%</div>
            <div class="stat-card"><svg viewBox="0 0 24 24" style="color:var(--blue)"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line></svg> RAM: <b id="ram">0</b>%</div>
        </div>

        <div id="panel-ui" style="display:none">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <h2 id="current-server-name" style="margin:0; font-size:16px;">Server</h2>
                <button onclick="openFiles()">File Manager</button>
            </div>
            
            <div id="console"></div>
            
            <div class="input-group">
                <input type="text" id="cmd-in" placeholder="Type command..." onkeydown="if(event.key==='Enter')sendCmd()">
                <button class="btn-blue" onclick="sendCmd()">Send</button>
            </div>
            
            <div class="input-group">
                <button class="btn-green" onclick="startSrv()" style="flex:1">Start</button>
                <button class="btn-red" onclick="stopSrv()" style="flex:1">Stop</button>
            </div>
        </div>
    </div>
</div>

<div id="file-modal" class="modal">
    <div class="modal-content">
        <div id="browser-ui" style="display:flex; flex-direction:column; height:100%;">
            <div style="padding:15px; display:flex; justify-content:space-between; background:var(--card); border-bottom:1px solid var(--border);">
                <span style="font-weight:bold;">File Manager</span>
                <button onclick="closeFiles()" class="btn-red">X</button>
            </div>
            <div class="file-list" id="browser-view"></div>
            <div style="padding:15px; background:var(--card); border-top:1px solid var(--border);">
                <input type="file" id="file-input">
                <button class="btn-blue" onclick="uploadFile()">Upload</button>
                <div class="progress-wrap" id="prog-wrap"><div class="progress-bar" id="prog-bar"></div></div>
            </div>
        </div>
        <div id="editor-view">
            <div style="padding:10px; background:var(--card); border-bottom:1px solid var(--border); display:flex; justify-content:space-between;">
                <span id="editing-filename"></span>
                <div><button onclick="backToBrowser()">Cancel</button> <button class="btn-green" onclick="saveFile()">Save</button></div>
            </div>
            <textarea id="file-content" spellcheck="false"></textarea>
        </div>
    </div>
</div>

<script>
    let activeServer = "";
    let editingFile = "";

    async function refreshServers() {
        const res = await fetch('/servers');
        const list = await res.json();
        document.getElementById('server-container').innerHTML = list.map(s => `
            <div class="server-item ${s===activeServer?'active':''}" onclick="selectServer('${s}')">
                <svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect></svg> ${s}
            </div>
        `).join('');
    }

    function selectServer(name) {
        activeServer = name;
        document.getElementById('panel-ui').style.display = 'block';
        document.getElementById('current-server-name').innerText = name;
        refreshServers();
        // Clear console immediately when switching
        document.getElementById('console').innerText = "Loading logs...";
    }

    async function createServer() {
        const name = document.getElementById('new-name').value;
        if(!name) return;
        await fetch('/create_server', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name}) });
        refreshServers();
    }

    function startSrv() { fetch(`/start/${activeServer}`, {method:'POST'}); }
    function stopSrv() { fetch(`/stop/${activeServer}`, {method:'POST'}); }
    function sendCmd() {
        const cmd = document.getElementById('cmd-in').value;
        fetch(`/command/${activeServer}`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({cmd}) });
        document.getElementById('cmd-in').value = "";
    }

    function openFiles() { document.getElementById('file-modal').style.display = 'flex'; loadFileList(); }
    function closeFiles() { document.getElementById('file-modal').style.display = 'none'; }

    async function loadFileList() {
        const res = await fetch(`/files/${activeServer}`);
        const files = await res.json();
        document.getElementById('browser-view').innerHTML = files.map(f => `
            <div class="file-row">
                <span>${f.is_dir ? '📁' : '📄'} ${f.name}</span>
                <div>
                    ${!f.is_dir ? `<button onclick="editFile('${f.name}')">Edit</button>` : ''}
                    <button onclick="deleteFile('${f.name}')">Del</button>
                </div>
            </div>
        `).join('');
    }

    async function editFile(f) {
        editingFile = f;
        const res = await fetch(`/read_file/${activeServer}/${f}`);
        document.getElementById('file-content').value = await res.text();
        document.getElementById('editing-filename').innerText = f;
        document.getElementById('browser-ui').style.display = 'none';
        document.getElementById('editor-view').style.display = 'flex';
    }

    function backToBrowser() { document.getElementById('browser-ui').style.display = 'flex'; document.getElementById('editor-view').style.display = 'none'; }

    async function saveFile() {
        await fetch(`/save_file/${activeServer}/${editingFile}`, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({content: document.getElementById('file-content').value})
        });
        backToBrowser();
    }

    function uploadFile() {
        const input = document.getElementById('file-input');
        if(!input.files[0]) return;
        const fd = new FormData(); fd.append('file', input.files[0]);
        const xhr = new XMLHttpRequest();
        document.getElementById('prog-wrap').style.display = 'block';
        xhr.upload.onprogress = (e) => { document.getElementById('prog-bar').style.width = (e.loaded/e.total)*100 + '%'; };
        xhr.onload = () => { document.getElementById('prog-wrap').style.display = 'none'; loadFileList(); };
        xhr.open('POST', `/upload/${activeServer}`);
        xhr.send(fd);
    }

    setInterval(async () => {
        const sRes = await fetch('/stats');
        const sData = await sRes.json();
        document.getElementById('cpu').innerText = sData.cpu;
        document.getElementById('ram').innerText = sData.ram;
        
        if(activeServer) {
            const lRes = await fetch(`/logs/${activeServer}`);
            const lData = await lRes.json();
            const box = document.getElementById('console');
            
            // Check if user is scrolled to bottom
            const isScrolledToBottom = box.scrollHeight - box.clientHeight <= box.scrollTop + 50;
            
            // Update text content
            box.innerText = lData.join('');
            
            // Auto-scroll if they were already at the bottom
            if (isScrolledToBottom) {
                box.scrollTop = box.scrollHeight;
            }
        }
    }, 1000);

    refreshServers();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
