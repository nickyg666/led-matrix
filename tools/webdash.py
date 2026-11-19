#!/usr/bin/env python3
"""Web dashboard for RP2040 8x32 LED matrix."""
import http.server
import json
import os
import select
import termios
import time
import glob

PORT = 8081
DEV = None


def find_device():
    devices = sorted(glob.glob("/dev/ttyACM*"))
    return devices[0] if devices else None


def send_cmd(cmd):
    global DEV
    if DEV is None:
        DEV = find_device()
    if not DEV:
        return "no device"
    fd = os.open(DEV, os.O_RDWR | os.O_NOCTTY)
    try:
        attrs = termios.tcgetattr(fd)
        attrs[1] = termios.OPOST | termios.ONLCR
        attrs[3] = termios.CREAD | termios.CLOCAL
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 1
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        while True:
            r, _, _ = select.select([fd], [], [], 0.05)
            if not r:
                break
            os.read(fd, 4096)
        os.write(fd, (cmd + "\r\n").encode())
        time.sleep(0.1)
        resp = b""
        while True:
            r, _, _ = select.select([fd], [], [], 0.3)
            if not r:
                break
            n = os.read(fd, 4096)
            if len(n) <= 0:
                break
            resp += n
        return resp.decode(errors="replace").strip() or "OK"
    finally:
        os.close(fd)


HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LED Matrix Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#06060a;--bg2:#0c0c14;--card:#12121c;--border:#1e1e2e;--accent:#6366f1;--accent2:#a855f7;--accent3:#22d3ee;--text:#e2e2f0;--muted:#555;--success:#10b981;--danger:#ef4444}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
body::before{content:'';position:fixed;top:0;left:0;right:0;bottom:0;background:radial-gradient(ellipse at 20% 20%,rgba(99,102,241,.1) 0%,transparent 50%),radial-gradient(ellipse at 80% 80%,rgba(34,211,238,.06) 0%,transparent 50%);pointer-events:none}
.container{max-width:1200px;margin:0 auto;padding:20px;position:relative;z-index:1}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid var(--border)}
.logo{font-size:24px;font-weight:700;background:linear-gradient(135deg,var(--accent),var(--accent2),var(--accent3));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{font-size:12px;color:var(--muted);margin-top:2px}
.status-dot{width:8px;height:8px;border-radius:50%;background:var(--success);display:inline-block;margin-right:6px;box-shadow:0 0 10px var(--success)}
.tabs{display:flex;gap:2px;margin-bottom:18px;background:var(--card);padding:4px;border-radius:12px;border:1px solid var(--border)}
.tab{flex:1;padding:10px 12px;text-align:center;cursor:pointer;border-radius:9px;font-size:13px;font-weight:500;color:var(--muted);transition:all .2s;border:none;background:none}
.tab:hover{color:var(--text);background:rgba(255,255,255,.04)}
.tab.active{color:#fff;background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 4px 16px rgba(99,102,241,.3)}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;margin:10px 0}
.card h2{font-size:15px;font-weight:600;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.card h2::before{content:'';width:3px;height:14px;background:linear-gradient(180deg,var(--accent),var(--accent2));border-radius:2px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0}
.btn{padding:9px 18px;border:none;border-radius:8px;background:linear-gradient(135deg,var(--accent),#4f46e5);color:#fff;cursor:pointer;font-weight:600;font-size:13px;transition:all .15s}
.btn:hover{transform:translateY(-1px);box-shadow:0 6px 18px rgba(99,102,241,.35)}
.btn:active{transform:translateY(0)}
.btn-sm{padding:5px 12px;font-size:11px}
.btn-danger{background:linear-gradient(135deg,var(--danger),#dc2626)}
.btn-success{background:linear-gradient(135deg,var(--success),#059669)}
.btn-ghost{background:transparent;border:1px solid var(--border);color:var(--muted)}
.btn-ghost:hover{border-color:var(--accent);color:var(--text);box-shadow:none}
input[type=color]{width:44px;height:36px;border:2px solid var(--border);border-radius:8px;cursor:pointer;background:none;padding:2px}
input[type=range]{width:160px;accent-color:var(--accent);cursor:pointer}
input[type=text],input[type=number],select{padding:7px 10px;border-radius:8px;background:var(--bg2);color:var(--text);border:1px solid var(--border);font-size:13px}
select{cursor:pointer;min-width:120px}
.label{font-size:11px;color:var(--muted);margin-right:4px;text-transform:uppercase;letter-spacing:.5px}
.matrix-preview{display:grid;gap:1px;background:#000;padding:4px;border-radius:8px;border:1px solid var(--border);margin:12px 0;max-width:100%;overflow:auto}
.matrix-cell{aspect-ratio:1;border-radius:1px;background:#111;min-width:8px}
.log{background:var(--bg2);padding:10px;border-radius:8px;font-family:'JetBrains Mono',monospace;font-size:11px;height:120px;overflow:auto;margin-top:8px;border:1px solid var(--border);color:#8f8}
.toast{position:fixed;bottom:20px;right:20px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;padding:12px 20px;border-radius:10px;font-weight:600;font-size:13px;opacity:0;transform:translateY(20px);transition:all .3s;pointer-events:none;z-index:100;box-shadow:0 8px 32px rgba(99,102,241,.3)}
.toast.show{opacity:1;transform:translateY(0)}
.status-bar{display:flex;align-items:center;gap:10px;padding:8px 14px;background:var(--bg2);border-radius:8px;font-size:12px;color:var(--muted);margin-top:8px}
.status-bar .dot{width:6px;height:6px;border-radius:50%;background:var(--success)}
@media(max-width:768px){.grid{grid-template-columns:1fr}.tabs{flex-wrap:wrap}.tab{flex:1 1 40%;font-size:12px;padding:8px 6px}.row{gap:6px}.btn{padding:8px 14px;font-size:12px}input[type=range]{width:120px}select{min-width:100px;font-size:12px}.matrix-preview{max-height:300px}.card{padding:14px;margin:8px 0}.container{padding:12px}header{flex-direction:column;gap:8px;align-items:flex-start}}
@media(max-width:480px){.tabs{gap:2px}.tab{flex:1 1 100%;font-size:11px;padding:6px}.row{flex-direction:column;align-items:stretch}.btn{width:100%}input[type=range]{width:100%}input[type=color]{width:100%;height:44px}select{width:100%}input[type=text],input[type=number]{width:100%}}
</style></head><body>
<div class="container">
<header>
  <div><div class="logo">LED Matrix Studio</div><div class="subtitle">RP2040 8x32 LED Matrix &middot; <span class="status-dot"></span>Connected</div></div>
  <div style="display:flex;gap:8px">
    <button class="btn btn-sm btn-ghost" onclick="refreshState()">Refresh</button>
  </div>
</header>
<div class="tabs">
  <button class="tab active" onclick="showTab('control',this)">Control</button>
  <button class="tab" onclick="showTab('text',this)">Text</button>
  <button class="tab" onclick="showTab('effects',this)">Effects</button>
  <button class="tab" onclick="showTab('image',this)">Image</button>
</div>

<!-- Control -->
<div id="tab-control">
<div class="grid">
<div class="card">
  <h2>Power & Brightness</h2>
  <div class="row">
    <button class="btn btn-danger" onclick="cmd('OFF')">Power Off</button>
    <button class="btn btn-success" onclick="cmd('ON')">Power On</button>
    <button class="btn btn-ghost" onclick="cmd('CLEAR')">Clear</button>
  </div>
  <div class="row">
    <span class="label">Brightness</span>
    <input type="range" id="bright" min="0" max="255" value="255" oninput="document.getElementById('bv').textContent=this.value">
    <span id="bv">255</span>
    <button class="btn btn-sm" onclick="cmd('BRIGHT '+document.getElementById('bright').value)">Set</button>
  </div>
  <div class="row">
    <span class="label">Speed</span>
    <input type="range" id="speed" min="1" max="255" value="5" oninput="document.getElementById('sv').textContent=this.value">
    <span id="sv">5</span>
    <button class="btn btn-sm" onclick="cmd('SPEED '+document.getElementById('speed').value)">Set</button>
  </div>
</div>
<div class="card">
  <h2>Status</h2>
  <div class="status-bar" id="status">Loading...</div>
  <button class="btn btn-sm btn-ghost" onclick="refreshState()" style="margin-top:8px">Refresh</button>
</div>
</div>
</div>

<!-- Text -->
<div id="tab-text" style="display:none">
<div class="card">
  <h2>Scrolling Text</h2>
  <div class="row">
    <input type="text" id="textinput" placeholder="Enter text..." style="flex:1;min-width:200px" value="HELLO WORLD">
    <button class="btn" onclick="applyText()">Set Text</button>
  </div>
  <div class="row">
    <span class="label">Text Color</span>
    <input type="color" id="textcolor" value="#ffffff">
    <button class="btn btn-sm" onclick="applyColor()">Set Color</button>
    <span class="label">Background</span>
    <input type="color" id="bgcolor" value="#000000">
    <button class="btn btn-sm" onclick="applyBg()">Set BG</button>
  </div>
  <div class="row">
    <button class="btn btn-sm" onclick="cmd('RAINBOWTEXT')">Rainbow Text ON</button>
    <button class="btn btn-sm btn-ghost" onclick="cmd('RAINBOWTEXTOFF')">Rainbow Text OFF</button>
  </div>
  <div class="row">
    <span class="label">Direction</span>
    <button class="btn btn-sm btn-ghost" onclick="cmd('DIR 1')">Left</button>
    <button class="btn btn-sm btn-ghost" onclick="cmd('DIR -1')">Right</button>
  </div>
</div>
</div>

<!-- Effects -->
<div id="tab-effects" style="display:none">
<div class="card">
  <h2>Effects</h2>
  <div class="row">
    <select id="effect" style="min-width:200px">
      <option value="text">Scrolling Text</option>
      <option value="rainbow">Rainbow</option>
      <option value="pulse">Pulse</option>
      <option value="wave">Wave</option>
      <option value="fire">Fire</option>
      <option value="matrix">Matrix</option>
      <option value="plasma">Plasma</option>
      <option value="sparkle">Sparkle</option>
    </select>
    <button class="btn" onclick="cmd('EFFECT '+document.getElementById('effect').value)">Start Effect</button>
    <button class="btn btn-danger" onclick="cmd('OFF')">Stop</button>
  </div>
  <p style="color:var(--muted);font-size:12px;margin-top:8px">Set a base color first (Text tab) for color-based effects.</p>
</div>
</div>

<!-- Image -->
<div id="tab-image" style="display:none">
<div class="card">
  <h2>Image Display</h2>
  <p style="color:var(--muted);font-size:12px;margin-bottom:10px">Send a 32x8 image. Use the grid below to paint, or paste hex data.</p>
  <div class="matrix-preview" id="imggrid" style="grid-template-columns:repeat(64,1fr)"></div>
  <div class="row" style="margin-top:8px">
    <button class="btn btn-sm btn-success" onclick="sendImage()">Send to Display</button>
    <button class="btn btn-sm btn-ghost" onclick="clearImage()">Clear</button>
    <button class="btn btn-sm btn-danger" onclick="cmd('CLEAR')">Clear Display</button>
  </div>
  <div class="row" style="margin-top:8px">
    <span class="label">Paint color</span>
    <input type="color" id="imgcolor" value="#ff0000">
  </div>
</div>
</div>

<div class="log" id="log"></div>
<div class="toast" id="toast"></div>
<script>
let imgColors=new Array(512).fill('#000000');
let isPainting=false;
function showTab(t,el){document.querySelectorAll('[id^=tab-]').forEach(e=>e.style.display='none');document.getElementById('tab-'+t).style.display='block';document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));el.classList.add('active');}
function log(msg){const l=document.getElementById('log');l.innerHTML+=msg+'<br>';l.scrollTop=l.scrollHeight;}
function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2000);}
function cmd(c){fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd:c})}).then(r=>r.text()).then(t=>log('> '+c+' => '+t.trim()));}
function applyText(){const t=document.getElementById('textinput').value;cmd('TEXT '+t);}
function applyColor(){const hex=document.getElementById('textcolor').value;const r=parseInt(hex.slice(1,3),16);const g=parseInt(hex.slice(3,5),16);const b=parseInt(hex.slice(5,7),16);cmd('COLOR '+r+' '+g+' '+b);}
function applyBg(){const hex=document.getElementById('bgcolor').value;const r=parseInt(hex.slice(1,3),16);const g=parseInt(hex.slice(3,5),16);const b=parseInt(hex.slice(5,7),16);cmd('BG '+r+' '+g+' '+b);}
function refreshState(){fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd:'PING'})}).then(r=>r.text()).then(t=>document.getElementById('status').textContent=t);}
// Image grid
const imggrid=document.getElementById('imggrid');
for(let i=0;i<512;i++){const d=document.createElement('div');d.className='matrix-cell';d.style.background='#000';d.dataset.idx=i;d.onmousedown=()=>{isPainting=true;paintImg(i);};d.onmouseenter=()=>{if(isPainting)paintImg(i);};d.onmouseup=()=>{isPainting=false;};imggrid.appendChild(d);}
document.onmouseup=()=>{isPainting=false;};
function paintImg(i){const hex=document.getElementById('imgcolor').value;imgColors[i]=hex;document.querySelectorAll('#imggrid .matrix-cell')[i].style.background=hex;}
function sendImage(){const hexes=imgColors.map(c=>c.replace('#',''));cmd('IMAGE '+hexes.join(','));}
function clearImage(){for(let i=0;i<512;i++){imgColors[i]='#000000';document.querySelectorAll('#imggrid .matrix-cell')[i].style.background='#000';}toast('Cleared');}
refreshState();
</script></body></html>"""

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}
        if self.path == "/api/cmd":
            resp = send_cmd(data.get("cmd", ""))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(resp.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    DEV = find_device()
    print(f"Device: {DEV}")
    print(f"Dashboard: http://0.0.0.0:{PORT}")
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
