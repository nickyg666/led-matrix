#!/usr/bin/env python3
"""LED Matrix Studio - clean, modern web dashboard for RP2350 8x32 matrix."""
import http.server
import json
import os
import select
import termios
import time
import glob
import threading

PORT = int(os.getenv("PORT", "8081"))
DEV = None
LOCK = threading.Lock()


def find_device():
    dev = os.getenv("SERIAL_DEVICE")
    if dev:
        return dev
    for p in ("/dev/rp2040-matrix", "/dev/ttyS5", "/dev/ttyS2", "/dev/ttyS0", "/dev/ttyACM0", "/dev/ttyACM1"):
        if os.path.exists(p):
            return p
    devices = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyS*"))
    return devices[0] if devices else None


def send_cmd(cmd):
    global DEV
    with LOCK:
        if DEV is None:
            DEV = find_device()
        if not DEV:
            return "no device"
        try:
            fd = os.open(DEV, os.O_RDWR | os.O_NOCTTY)
        except OSError as e:
            DEV = None
            return "open err: %s" % e
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
                if not n:
                    break
                resp += n
            r = resp.decode(errors="replace").strip()
            return r if r else "OK"
        except OSError as e:
            DEV = None
            return "err: %s" % e
        finally:
            try:
                os.close(fd)
            except OSError:
                pass


def send_frame(rgb):
    global DEV
    if not isinstance(rgb, list) or len(rgb) != 256 * 3:
        return "ERR: expected 768 values"
    safe = []
    for v in rgb:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return "ERR: non-integer color"
        safe.append(max(0, min(255, n)))
    payload = bytes(safe)
    with LOCK:
        if DEV is None:
            DEV = find_device()
        if not DEV:
            return "no device"
        try:
            fd = os.open(DEV, os.O_RDWR | os.O_NOCTTY)
        except OSError as e:
            DEV = None
            return "open err: %s" % e
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
            os.write(fd, b"IMGB\r\n")
            time.sleep(0.02)
            os.write(fd, payload)
            time.sleep(0.06)
            resp = b""
            while True:
                r, _, _ = select.select([fd], [], [], 0.2)
                if not r:
                    break
                n = os.read(fd, 4096)
                if not n:
                    break
                resp += n
            return resp.decode(errors="replace").strip() or "OK"
        except OSError as e:
            DEV = None
            return "err: %s" % e
        finally:
            try:
                os.close(fd)
            except OSError:
                pass


HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LED Matrix</title>
<style>
:root{--bg:#08080d;--bg2:#0f0f18;--card:#14141f;--border:#1e1e2e;--accent:#6366f1;--accent2:#a855f7;--text:#e2e2f0;--muted:#666;--danger:#ef4444;--success:#10b981;--warn:#f59e0b}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.container{max-width:1000px;margin:0 auto;padding:16px}
h1{font-size:22px;margin-bottom:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
h2{font-size:14px;margin:12px 0 6px;color:#8af}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px;margin:8px 0}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:6px 0}
.btn{padding:8px 16px;border:none;border-radius:6px;background:var(--accent);color:#fff;cursor:pointer;font-size:13px;font-weight:600}
.btn:hover{opacity:.9}
.btn-danger{background:var(--danger)}
.btn-success{background:var(--success)}
.btn-ghost{background:transparent;border:1px solid var(--border);color:var(--muted)}
input[type=text]{padding:8px;border-radius:6px;background:var(--bg2);color:#eee;border:1px solid var(--border);flex:1;min-width:120px}
input[type=range]{width:160px;accent-color:var(--accent)}
select{padding:8px;border-radius:6px;background:var(--bg2);color:#eee;border:1px solid var(--border)}
.label{font-size:11px;color:var(--muted);margin-right:4px;text-transform:uppercase;letter-spacing:.5px}
.toggle{display:flex;align-items:center;gap:6px;padding:6px 12px;border-radius:6px;background:var(--bg2);border:1px solid var(--border);cursor:pointer;font-size:13px}
.toggle.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.toggle input{display:none}
.matrix{display:grid;gap:1px;background:#000;padding:3px;border-radius:6px;margin:8px 0;overflow:auto}
.cell{aspect-ratio:1;border-radius:1px;background:#111;min-width:6px;cursor:pointer}
.log{background:var(--bg2);padding:8px;border-radius:6px;font-family:monospace;font-size:11px;height:80px;overflow:auto;margin-top:8px;color:#8f8}
.tabs{display:flex;gap:4px;margin-bottom:12px}
.tab{padding:8px 16px;cursor:pointer;border-radius:6px;background:#222;color:var(--muted);border:none;font-size:13px}
.tab.active{background:var(--accent);color:#fff}
.game-canvas{background:#000;border-radius:6px;border:1px solid var(--border);max-width:100%;touch-action:none}
.ctrl{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin:8px 0;max-width:200px}
.ctrl button{padding:12px 8px;font-size:18px;border:none;border-radius:6px;background:#333;color:#fff;cursor:pointer;touch-action:manipulation}
.ctrl button:active{background:var(--accent)}
@media(max-width:600px){.row{flex-direction:column;align-items:stretch}.btn{width:100%}input[type=range]{width:100%}select{width:100%}input[type=text]{width:100%}.tabs{flex-wrap:wrap}.tab{flex:1 1 40%}}
</style></head><body>
<div class="container">
<h1>LED Matrix</h1>
<div class="tabs">
  <button class="tab active" onclick="showTab('text',this)">Text</button>
  <button class="tab" onclick="showTab('control',this)">Control</button>
  <button class="tab" onclick="showTab('image',this)">Image</button>
  <button class="tab" onclick="showTab('games',this)">Games</button>
</div>

<!-- Text -->
<div id="tab-text">
<div class="card">
  <h2>Scrolling Text</h2>
  <div class="row">
    <input type="text" id="text" value="TEST" placeholder="Enter text">
    <button class="btn" onclick="applyText()">Set</button>
  </div>
  <div class="row">
    <label class="toggle" onclick="this.classList.toggle('on');cmd('RAINBOWTEXT')"><input type="checkbox">Rainbow</label>
    <label class="toggle" onclick="this.classList.toggle('on');cmd('VFLIP')"><input type="checkbox">Upside Down</label>
    <label class="toggle" onclick="this.classList.toggle('on');cmd('HFLIP')"><input type="checkbox">Reversed</label>
  </div>
  <div class="row">
    <span class="label">Color</span>
    <input type="color" id="tcol" value="#ffffff">
    <button class="btn btn-ghost" onclick="applyColor()">Set</button>
    <span class="label">BG</span>
    <input type="color" id="bgcol" value="#000000">
    <button class="btn btn-ghost" onclick="applyBg()">Set BG</button>
  </div>
  <div class="row">
    <span class="label">Direction</span>
    <input type="range" id="dir" min="-1" max="1" value="1" step="2" oninput="document.getElementById('dirv').textContent=this.value==1?'Right':'Left'">
    <span id="dirv">Right</span>
    <button class="btn btn-ghost" onclick="cmd('DIR '+document.getElementById('dir').value)">Set</button>
  </div>
  <div class="row">
    <span class="label">Brightness</span>
    <input type="range" id="bright" min="0" max="255" value="128" oninput="document.getElementById('bv').textContent=this.value">
    <span id="bv">128</span>
    <button class="btn btn-ghost" onclick="cmd('BRIGHT '+document.getElementById('bright').value)">Set</button>
  </div>
  <div class="row">
    <span class="label">Speed</span>
    <input type="range" id="speed" min="1" max="255" value="5" oninput="document.getElementById('sv').textContent=this.value">
    <span id="sv">5</span>
    <button class="btn btn-ghost" onclick="cmd('SPEED '+document.getElementById('speed').value)">Set</button>
  </div>
</div>
</div>

<!-- Control -->
<div id="tab-control" style="display:none">
<div class="card">
  <h2>Power & Effects</h2>
  <div class="row">
    <button class="btn" onclick="cmd('OFF')">Off</button>
    <button class="btn" onclick="cmd('ON')">On</button>
    <button class="btn btn-ghost" onclick="cmd('CLEAR')">Clear</button>
  </div>
  <div class="row">
    <select id="effect">
      <option value="text">Text</option>
      <option value="bounce">Bounce</option>
      <option value="rainbow">Rainbow</option>
      <option value="pulse">Pulse</option>
      <option value="wave">Wave</option>
      <option value="fire">Fire</option>
      <option value="matrix">Matrix</option>
      <option value="plasma">Plasma</option>
      <option value="sparkle">Sparkle</option>
    </select>
    <button class="btn" onclick="cmd('EFFECT '+document.getElementById('effect').value)">Start</button>
  </div>
  <div class="row">
    <span class="label">Serial</span>
    <select id="sport"><option value="/dev/ttyS0">ttyS0</option><option value="/dev/ttyS2">ttyS2</option><option value="/dev/ttyACM0">ttyACM0</option><option value="/dev/ttyACM1">ttyACM1</option></select>
    <button class="btn btn-ghost" onclick="setPort()">Connect</button>
    <span id="portstatus" style="font-size:11px;color:var(--muted)"></span>
  </div>
</div>
</div>

<!-- Image -->
<div id="tab-image" style="display:none">
<div class="card">
  <h2>Image (8x32)</h2>
  <div class="matrix" id="imggrid" style="grid-template-columns:repeat(32,1fr)"></div>
  <div class="row">
    <input type="color" id="imgcolor" value="#ff0000">
    <button class="btn btn-ghost" onclick="sendImage()">Send</button>
    <button class="btn btn-ghost" onclick="clearImg()">Clear</button>
    <button class="btn btn-ghost" onclick="cmd('CLEAR')">Clear Display</button>
  </div>
</div>
</div>

<!-- Games -->
<div id="tab-games" style="display:none">
<div class="card">
  <h2>Arcade</h2>
  <div class="row">
    <select id="game"><option value="snake">Snake</option><option value="invaders">Space Invaders</option><option value="breakout">Breakout</option><option value="pong">Pong</option></select>
    <button class="btn" onclick="startGame()">Start</button>
    <button class="btn btn-danger" onclick="stopGame()">Stop</button>
  </div>
  <div class="row">
    <span class="label">Score</span><span id="score">0</span>
    <span class="label">Lives</span><span id="lives">3</span>
  </div>
  <canvas id="gameCanvas" class="game-canvas" width="320" height="80"></canvas>
  <div class="ctrl">
    <button onclick="keys['ArrowLeft']=true;setTimeout(()=>keys['ArrowLeft']=false,150)">&#9664;</button>
    <button onclick="keys['ArrowUp']=true;setTimeout(()=>keys['ArrowUp']=false,150)">&#9650;</button>
    <button onclick="keys['ArrowRight']=true;setTimeout(()=>keys['ArrowRight']=false,150)">&#9654;</button>
    <button onclick="keys['ArrowDown']=true;setTimeout(()=>keys['ArrowDown']=false,150)">&#9660;</button>
    <button onclick="keys[' ']=true;setTimeout(()=>keys[' ']=false,150)">FIRE</button>
    <button onclick="keys['r']=true;setTimeout(()=>keys['r']=false,150)">RST</button>
  </div>
  <div class="matrix" id="gamegrid" style="grid-template-columns:repeat(32,1fr)"></div>
</div>
</div>

<div class="log" id="log"></div>
<script>
let W=32,H=8,grid=[],timer=null,game=null,keys={},score=0,lives=3;
function showTab(t,el){document.querySelectorAll('[id^=tab-]').forEach(e=>e.style.display='none');document.getElementById('tab-'+t).style.display='block';document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));el.classList.add('active');}
function log(m){const l=document.getElementById('log');l.innerHTML+=m+'<br>';l.scrollTop=l.scrollHeight}
function cmd(c){fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd:c})}).then(r=>r.text()).then(t=>log('> '+c+' -> '+t.trim()))}
function applyText(){cmd('TEXT '+document.getElementById('text').value)}
function applyColor(){const h=document.getElementById('tcol').value;cmd('COLOR '+parseInt(h.slice(1,3),16)+' '+parseInt(h.slice(3,5),16)+' '+parseInt(h.slice(5,7),16))}
function applyBg(){const h=document.getElementById('bgcol').value;cmd('BG '+parseInt(h.slice(1,3),16)+' '+parseInt(h.slice(3,5),16)+' '+parseInt(h.slice(5,7),16))}
function setPort(){const p=document.getElementById('sport').value;fetch('/api/port',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port:p})}).then(r=>r.text()).then(t=>log('port: '+t.trim()))}
function makeGrid(){grid=new Array(W*H).fill('#000000')}
function renderGrid(){const g=document.getElementById('gamegrid');for(let i=0;i<g.children.length;i++)g.children[i].style.background=grid[i]}
function setPix(x,y,c){if(x<0||x>=W||y<0||y>=H)return;grid[y*W+x]=c}
function resetGrid(){for(let i=0;i<grid.length;i++)grid[i]='#000000'}
function sendFrame(){fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd:'FRAME '+grid.map(c=>c.replace('#','')).join(',')})})}
function drawGame(){let c=document.getElementById('gameCanvas'),x=c.getContext('2d'),s=10;x.fillStyle='#000';x.fillRect(0,0,c.width,c.height);for(let y=0;y<H;y++)for(let px=0;px<W;px++){let col=grid[y*W+px];if(col!=='#000000'){x.fillStyle=col;x.fillRect(px*s,y*s,s-1,s-1)}}renderGrid()}
function tick(){if(!game)return;if(game==='snake')tickSnake();else if(game==='invaders')tickInvaders();else if(game==='breakout')tickBreakout();else tickPong();drawGame();sendFrame();document.getElementById('score').textContent=score;document.getElementById('lives').textContent=lives}
function startGame(){stopGame();game=document.getElementById('game').value;score=0;lives=3;resetGrid();if(game==='snake')initSnake();else if(game==='invaders')initInvaders();else if(game==='breakout')initBreakout();else initPong();timer=setInterval(tick,120);log('started '+game)}
function stopGame(){if(timer)clearInterval(timer);timer=null;game=null;keys={};cmd('CLEAR')}
window.addEventListener('keydown',e=>{keys[e.key]=true;if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown',' ','a','d','w','s','r'].includes(e.key))e.preventDefault()});
window.addEventListener('keyup',e=>keys[e.key]=false);
function initSnake(){S={b:[{x:16,y:4},{x:15,y:4},{x:14,y:4}],d:{x:1,y:0},f:{x:8,y:4}};placeFood()}
function placeFood(){do{S.f={x:Math.floor(Math.random()*W),y:Math.floor(Math.random()*H)}}while(S.b.some(p=>p.x===S.f.x&&p.y===S.f.y))}
function tickSnake(){let k=keys;if(k.ArrowLeft||k.a)S.d={x:-1,y:0};else if(k.ArrowRight||k.d)S.d={x:1,y:0};else if(k.ArrowUp||k.w)S.d={x:0,y:-1};else if(k.ArrowDown||k.s)S.d={x:0,y:1};let h={x:S.b[0].x+S.d.x,y:S.b[0].y+S.d.y};if(h.x<0||h.x>=W||h.y<0||h.y>=H||S.b.some(p=>p.x===h.x&&p.y===h.y)){lives--;if(lives<=0){initSnake();lives=3}else initSnake();return}S.b.unshift(h);if(h.x===S.f.x&&h.y===S.f.y){score+=10;placeFood()}else S.b.pop();resetGrid();S.b.forEach((p,i)=>setPix(p.x,p.y,i?'#0a8':'#4af'));setPix(S.f.x,S.f.y,'#f44')}
function initInvaders(){I={p:16,inv:[],b:[],dx:1,t:0};for(let r=0;r<2;r++)for(let c=0;c<8;c++)I.inv.push({x:2+c*3,y:1+r*2,alive:true})}
function tickInvaders(){I.t++;if(keys.ArrowLeft||keys.a)I.p=Math.max(0,I.p-1);if(keys.ArrowRight||keys.d)I.p=Math.min(W-2,I.p+1);if(keys[' ']&&I.t%4===0)I.b.push({x:I.p,y:H-2,dir:-1});I.b.forEach(b=>b.y+=b.dir);I.b=I.b.filter(b=>b.y>=0&&b.y<H);if(I.t%6===0){let edge=I.inv.some(i=>i.alive&&(i.x<=0&&I.dx<0||i.x>=W-2&&I.dx>0));if(edge){I.dx*=-1;I.inv.forEach(i=>i.y++)}else I.inv.forEach(i=>i.x+=I.dx)}if(I.t%4===0)I.inv.filter(i=>i.alive).forEach(i=>{if(Math.random()<0.06)I.b.push({x:i.x,y:i.y+1,dir:1})});I.b.forEach(b=>{I.inv.forEach(i=>{if(i.alive&&b.x>=i.x&&b.x<=i.x+1&&b.y===i.y){i.alive=false;b.y=-1;score+=10}})});I.b=I.b.filter(b=>b.y>=0);if(I.inv.some(i=>i.alive&&i.y>=H-2)){lives--;initInvaders()}resetGrid();I.inv.filter(i=>i.alive).forEach(i=>{setPix(i.x,i.y,'#4f4');setPix(i.x+1,i.y,'#4f4')});I.b.forEach(b=>setPix(b.x,b.y,'#ff0'));setPix(I.p,H-1,'#4af');setPix(I.p+1,H-1,'#4af')}
function initBreakout(){B={p:14,x:16,y:H-3,vx:1,vy:-1,bricks:[]};for(let r=0;r<2;r++)for(let c=0;c<10;c++)B.bricks.push({x:1+c*3,y:1+r,alive:true})}
function tickBreakout(){if(keys.ArrowLeft||keys.a)B.p=Math.max(0,B.p-2);if(keys.ArrowRight||keys.d)B.p=Math.min(W-3,B.p+2);B.x+=B.vx;B.y+=B.vy;if(B.x<=0||B.x>=W-1)B.vx*=-1;if(B.y<=0)B.vy*=-1;if(B.y>=H-2&&B.x>=B.p&&B.x<=B.p+2){B.vy*=-1;B.vx=(B.x-B.p-1)/2||1}if(B.y>=H){lives--;if(lives<=0){initBreakout();lives=3}else{B.x=16;B.y=H-3;B.vy=-1}}B.bricks.forEach(b=>{if(b.alive&&B.x>=b.x&&B.x<=b.x+2&&B.y===b.y){b.alive=false;B.vy*=-1;score+=10}});resetGrid();B.bricks.filter(b=>b.alive).forEach(b=>{for(let d=0;d<3;d++)setPix(b.x+d,b.y,'#f84')});for(let d=0;d<3;d++)setPix(B.p+d,H-1,'#4af');setPix(Math.round(B.x),Math.round(B.y),'#fff')}
function initPong(){P={a:2,b:H/2-1,cpu:W-4,ball:{x:W/2,y:H/2,vx:1,vy:1}}}
function tickPong(){if(keys.ArrowUp||keys.w)P.b=Math.max(0,P.b-1);if(keys.ArrowDown||keys.s)P.b=Math.min(H-2,P.b+1);let b=P.ball;b.x+=b.vx;b.y+=b.vy;if(b.y<=0||b.y>=H-1)b.vy*=-1;if(b.x<=P.a+1&&b.y>=P.b&&b.y<=P.b+1){b.vx*=-1;b.vy=(b.y-P.b)/2||1}if(b.x>=P.cpu-1){if(b.y>=P.cpu&&b.y<=P.cpu+1){b.vx*=-1;b.vy=(b.y-P.cpu)/2||1}else{score+=10;initPong();return}}if(b.x<0){lives--;if(lives<=0){initPong();lives=3}else initPong()}let cy=Math.floor(b.y);P.cpu=Math.max(0,Math.min(H-2,cy));resetGrid();for(let d=0;d<2;d++){setPix(P.a,P.b+d,'#4af');setPix(P.cpu,P.cpu+d,'#f44')}setPix(Math.floor(b.x),Math.floor(b.y),'#fff')}
makeGrid();document.getElementById('score').textContent=score;document.getElementById('lives').textContent=lives;
</script></body></html>"""

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
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
            resp = send_cmd(str(data.get("cmd", "")))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(resp.encode())
        elif self.path == "/api/port":
            global DEV
            DEV = data.get("port")
            resp = send_cmd("PING")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write((resp if resp else "no response").encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    DEV = find_device()
    print("Device: %s" % DEV)
    print("Dashboard: http://0.0.0.0:%d" % PORT)
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
PYEOF
