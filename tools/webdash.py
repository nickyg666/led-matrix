#!/usr/bin/env python3
"""LED Matrix Studio web dashboard."""
import http.server
import json
import os
import select
import termios
import time
import glob
import threading

PORT = 8081
DEV = None
LOCK = threading.Lock()


def find_device():
    for p in ("/dev/rp2040-matrix", "/dev/rp2040-rgb"):
        if os.path.exists(p):
            return p
    devices = sorted(glob.glob("/dev/ttyACM*"))
    return devices[0] if devices else None


def setup(fd):
    attrs = termios.tcgetattr(fd)
    attrs[1] = termios.OPOST | termios.ONLCR
    attrs[3] = termios.CREAD | termios.CLOCAL
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def drain(fd, wait=0.05):
    while True:
        r, _, _ = select.select([fd], [], [], wait)
        if not r:
            break
        try:
            if not os.read(fd, 4096):
                break
        except OSError:
            break


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
            setup(fd)
            drain(fd)
            os.write(fd, (cmd + "\r\n").encode())
            time.sleep(0.08)
            resp = b""
            while True:
                r, _, _ = select.select([fd], [], [], 0.25)
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


def send_frame(rgb):
    global DEV
    payload = bytes(rgb)
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
            setup(fd)
            drain(fd)
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
<title>LED Matrix Studio</title>
<style>
:root{--bg:#06060a;--bg2:#0c0c14;--card:#12121c;--border:#1e1e2e;--a:#6366f1;--b:#a855f7;--c:#22d3ee;--txt:#e2e2f0;--mut:#666;--ok:#10b981;--bad:#ef4444}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--txt);min-height:100vh}
.container{max-width:1200px;margin:0 auto;padding:18px}
.logo{font-size:23px;font-weight:700;background:linear-gradient(135deg,var(--a),var(--b),var(--c));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sub{font-size:12px;color:var(--mut);margin-top:2px}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.tabs{display:flex;gap:3px;margin-bottom:14px;background:var(--card);padding:4px;border-radius:10px;border:1px solid var(--border);flex-wrap:wrap}
.tab{flex:1;padding:9px;cursor:pointer;border:0;border-radius:8px;background:none;color:var(--mut);font-size:13px}
.tab.active{color:#fff;background:linear-gradient(135deg,var(--a),var(--b))}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin:8px 0}
.card h2{font-size:15px;margin-bottom:10px;color:var(--c)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:7px 0}
.btn{padding:8px 14px;border:0;border-radius:8px;background:linear-gradient(135deg,var(--a),#4f46e5);color:#fff;cursor:pointer;font-size:13px}
.btn.sm{padding:5px 10px;font-size:11px}
.btn.ghost{background:transparent;border:1px solid var(--border);color:var(--mut)}
.btn.danger{background:linear-gradient(135deg,var(--bad),#dc2626)}
.btn.ok{background:linear-gradient(135deg,var(--ok),#059669)}
input[type=color]{width:40px;height:32px;border:2px solid var(--border);border-radius:6px;background:none;cursor:pointer}
input[type=range]{width:150px}
input[type=text],input[type=number],select{padding:6px 9px;border-radius:7px;background:var(--bg2);color:var(--txt);border:1px solid var(--border)}
.label{font-size:11px;color:var(--mut);text-transform:uppercase;margin-right:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.preview{display:grid;gap:1px;background:#000;padding:3px;border-radius:7px;border:1px solid var(--border);margin:10px 0;max-width:100%;overflow:auto}
.cell{aspect-ratio:1;border-radius:1px;background:#111;min-width:6px;cursor:pointer}
.log{background:var(--bg2);padding:9px;border-radius:7px;font-family:monospace;font-size:11px;height:110px;overflow:auto;margin-top:8px;color:#8f8}
.toast{position:fixed;bottom:18px;right:18px;background:linear-gradient(135deg,var(--a),var(--b));padding:11px 18px;border-radius:9px;opacity:0;transition:.3s;pointer-events:none;z-index:99}
.toast.show{opacity:1}
.status{font-size:12px;color:var(--mut);background:var(--bg2);padding:8px;border-radius:7px}
canvas{max-width:100%;border:1px solid var(--border);border-radius:7px;background:#000}
.keys{font-family:monospace;color:var(--c);font-size:12px;margin-top:5px}
@media(max-width:768px){.tabs{flex-direction:column}.tab{flex:none}.row{gap:5px}input[type=range]{width:100%}.btn{width:100%}}
</style></head><body>
<div class="container">
<header><div><div class="logo">LED Matrix Studio</div><div class="sub">RP2040 matrix &middot; 8x64 / 16x32</div></div><button class="btn sm ghost" onclick="refresh()">Refresh</button></header>
<div class="tabs">
<button class="tab active" id="t-control" onclick="show('control')">Control</button>
<button class="tab" id="t-text" onclick="show('text')">Text</button>
<button class="tab" id="t-effects" onclick="show('effects')">Effects</button>
<button class="tab" id="t-image" onclick="show('image')">Image</button>
<button class="tab" id="t-games" onclick="show('games')">Games</button>
</div>

<div id="p-control"><div class="grid"><div class="card"><h2>Power & Layout</h2>
<div class="row"><button class="btn danger" onclick="cmd('OFF')">Off</button><button class="btn ok" onclick="cmd('ON')">On</button><button class="btn ghost" onclick="cmd('CLEAR')">Clear</button></div>
<div class="row"><span class="label">Layout</span><button class="btn sm" onclick="layout(0)">8 x 64</button><button class="btn sm" onclick="layout(1)">16 x 32</button></div>
<div class="row"><span class="label">Brightness</span><input type="range" id="bright" min="0" max="26" value="26" oninput="document.getElementById('bv').textContent=this.value"><span id="bv">26</span><button class="btn sm" onclick="cmd('BRIGHT '+bright.value)">Set</button></div>
<div class="row"><span class="label">Speed</span><input type="range" id="speed" min="1" max="255" value="24" oninput="document.getElementById('sv').textContent=this.value"><span id="sv">24</span><button class="btn sm" onclick="cmd('SPEED '+speed.value)">Set</button></div>
<div class="row"><button class="btn sm ghost" onclick="cmd('VFLIP')">VFLIP</button><button class="btn sm ghost" onclick="cmd('SERP')">SERP</button><button class="btn sm ghost" onclick="cmd('MIRROR')">MIRROR</button><button class="btn sm ghost" onclick="cmd('BASE 0')">BASE0</button><button class="btn sm ghost" onclick="cmd('BASE 1')">BASE1</button></div>
</div><div class="card"><h2>Status</h2><div class="status" id="status">Loading...</div></div></div></div>

<div id="p-text" style="display:none"><div class="card"><h2>Scrolling Text</h2>
<div class="row"><input type="text" id="text" style="flex:1;min-width:220px" value="the quick brown fox jumped over the lazy dog"><button class="btn" onclick="cmd('TEXT '+text.value)">Set</button></div>
<div class="row"><span class="label">Color</span><input type="color" id="tcol" value="#ffffff"><button class="btn sm" onclick="applyColor()">Set</button><span class="label">BG</span><input type="color" id="bgcol" value="#000000"><button class="btn sm" onclick="applyBg()">Set BG</button></div>
<div class="row"><button class="btn sm" onclick="cmd('RAINBOWTEXT')">Rainbow on</button><button class="btn sm ghost" onclick="cmd('RAINBOWTEXTOFF')">Rainbow off</button><button class="btn sm ghost" onclick="cmd('DIR 1')">Left</button><button class="btn sm ghost" onclick="cmd('DIR -1')">Right</button></div>
</div></div>

<div id="p-effects" style="display:none"><div class="card"><h2>Effects</h2><div class="row"><select id="effect"><option value="text">Text</option><option value="rainbow">Rainbow</option><option value="pulse">Pulse</option><option value="wave">Wave</option><option value="fire">Fire</option><option value="matrix">Matrix</option><option value="plasma">Plasma</option><option value="sparkle">Sparkle</option></select><button class="btn" onclick="cmd('EFFECT '+effect.value)">Start</button><button class="btn danger" onclick="cmd('OFF')">Stop</button></div></div></div>

<div id="p-image" style="display:none"><div class="card"><h2>Image Converter</h2>
<div class="row"><input type="file" id="imgfile" accept="image/*"><button class="btn" onclick="convertImage()">Convert & Send</button></div>
<div class="row"><span class="label">Fit</span><select id="fit"><option value="contain">Contain</option><option value="stretch">Stretch</option><option value="cover">Cover</option></select><span class="label">Mode</span><select id="mode"><option value="color">Color</option><option value="mono">Mono</option><option value="dither">Dither</option></select><button class="btn sm ghost" onclick="clearImage()">Clear</button></div>
<canvas id="src" width="64" height="8"></canvas><div class="preview" id="grid"></div><button class="btn ok" onclick="renderFrame()">Send Frame</button>
</div></div>

<div id="p-games" style="display:none"><div class="card"><h2>Arcade</h2>
<div class="row"><select id="game"><option value="invaders">Space Invaders</option><option value="snake">Snake</option><option value="breakout">Breakout</option><option value="pong">Pong</option></select><button class="btn ok" onclick="startGame()">Start</button><button class="btn danger" onclick="stopGame()">Stop</button><button class="btn ghost" onclick="layout(1)">Force 16x32</button></div>
<div class="row"><span class="label">Score</span><span id="score">0</span><span class="label">Lives</span><span id="lives">3</span></div>
<canvas id="gameCanvas" width="320" height="160"></canvas><div class="keys" id="help">Arrows / A,D move &middot; Space fire &middot; R restart</div><div class="preview" id="gamegrid"></div>
</div></div>

<div class="log" id="log"></div><div class="toast" id="toast"></div>
<script>
let W=64,H=8,grid=[],timer=null,game=null,keys={},score=0,lives=3;
function log(m){const l=document.getElementById('log');l.innerHTML+=m+'<br>';l.scrollTop=l.scrollHeight}
function toast(m){const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1800)}
function cmd(c){fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd:c})}).then(r=>r.text()).then(t=>{log('> '+c+' -> '+t.trim());if(c.startsWith('STATE'))document.getElementById('status').textContent=t.trim()})}
function refresh(){cmd('STATE')}
function show(n){document.querySelectorAll('[id^=p-]').forEach(e=>e.style.display='none');document.getElementById('p-'+n).style.display='';document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));document.getElementById('t-'+n).classList.add('active')}
function layout(l){cmd('LAYOUT '+l);W=l?32:64;H=l?16:8;buildGrids()}
function makeGrid(el){el.innerHTML='';let a=[];for(let i=0;i<W*H;i++){let d=document.createElement('div');d.className='cell';d.style.background='#000';el.appendChild(d);a.push('#000000')}return a}
function buildGrids(){grid=makeGrid(document.getElementById('grid'));makeGrid(document.getElementById('gamegrid'));let c=document.getElementById('gameCanvas');c.width=W*10;c.height=H*10}
function setPix(x,y,col){if(x<0||x>=W||y<0||y>=H)return;grid[y*W+x]=col}
function renderGrid(){const el=document.getElementById('grid');for(let i=0;i<grid.length;i++)if(el.children[i])el.children[i].style.background=grid[i]}
function rgbArray(){let a=[];for(let c of grid){let h=c.replace('#','');a.push(parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16))}return a}
function renderFrame(){fetch('/api/frame',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rgb:rgbArray()})}).then(r=>r.text()).then(t=>log('frame -> '+t.trim()))}
function clearImage(){grid=grid.map(()=> '#000000');renderGrid()}
function applyColor(){let h=document.getElementById('tcol').value;cmd('COLOR '+parseInt(h.slice(1,3),16)+' '+parseInt(h.slice(3,5),16)+' '+parseInt(h.slice(5,7),16))}
function applyBg(){let h=document.getElementById('bgcol').value;cmd('BG '+parseInt(h.slice(1,3),16)+' '+parseInt(h.slice(3,5),16)+' '+parseInt(h.slice(5,7),16))}
function convertImage(){let f=document.getElementById('imgfile').files[0];if(!f){toast('Choose an image');return}let img=new Image();img.onload=()=>{let c=document.getElementById('src');c.width=W;c.height=H;let x=c.getContext('2d');x.fillStyle='#000';x.fillRect(0,0,W,H);let fit=document.getElementById('fit').value;let iw=img.width,ih=img.height;if(fit==='stretch')x.drawImage(img,0,0,W,H);else{let s=Math.min(W/iw,H/ih);if(fit==='cover')s=Math.max(W/iw,H/ih);let w=iw*s,h=ih*s;x.drawImage(img,(W-w)/2,(H-h)/2,w,h)}let d=x.getImageData(0,0,W,H).data;let mode=document.getElementById('mode').value;let bayer=[0,8,2,10,12,4,14,6,3,11,1,9,15,7,13,5];for(let y=0;y<H;y++)for(let px=0;px<W;px++){let i=(y*W+px)*4,r=d[i],g=d[i+1],b=d[i+2];if(mode==='mono'){let v=(r+g+b)/3>128?255:0;setPix(px,y,'#'+v.toString(16).padStart(2,'0').repeat(3))}else if(mode==='dither'){let v=(r+g+b)/3+bayer[(y%4)*4+(px%4)]*16;v=v>127?255:0;setPix(px,y,'#'+v.toString(16).padStart(2,'0').repeat(3))}else setPix(px,y,'#'+[r,g,b].map(n=>n.toString(16).padStart(2,'0')).join(''))}renderGrid();renderFrame();toast('Converted '+iw+'x'+ih)};img.src=URL.createObjectURL(f)}
window.addEventListener('keydown',e=>{keys[e.key]=true;if(game&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown',' ','a','d','w','s'].includes(e.key))e.preventDefault()});
window.addEventListener('keyup',e=>keys[e.key]=false);
function drawGame(){let c=document.getElementById('gameCanvas'),x=c.getContext('2d'),s=10;x.fillStyle='#000';x.fillRect(0,0,c.width,c.height);for(let y=0;y<H;y++)for(let px=0;px<W;px++){let col=grid[y*W+px];if(col!=='#000000'){x.fillStyle=col;x.fillRect(px*s,y*s,s-1,s-1)}}let g=document.getElementById('gamegrid');for(let i=0;i<g.children.length;i++)g.children[i].style.background=grid[i]}
function tick(){if(!game)return;if(game==='snake')tickSnake();else if(game==='invaders')tickInvaders();else if(game==='breakout')tickBreakout();else tickPong();drawGame();renderFrame();document.getElementById('score').textContent=score;document.getElementById('lives').textContent=lives}
function resetGrid(){grid=grid.map(()=> '#000000')}
function startGame(){stopGame();let g=document.getElementById('game').value;if(g!=='snake')layout(1);else layout(1);game=g;score=0;lives=3;resetGrid();if(g==='snake')initSnake();else if(g==='invaders')initInvaders();else if(g==='breakout')initBreakout();else initPong();timer=setInterval(tick,120);toast('Started '+g)}
function stopGame(){if(timer)clearInterval(timer);timer=null;game=null;keys={}}
function initSnake(){S={b:[{x:8,y:8},{x:7,y:8},{x:6,y:8}],d:{x:1,y:0},f:{x:16,y:8}};placeFood()}
function placeFood(){do{S.f={x:Math.floor(Math.random()*W),y:Math.floor(Math.random()*H)}}while(S.b.some(p=>p.x===S.f.x&&p.y===S.f.y))}
function tickSnake(){let k=keys;if(k.ArrowLeft||k.a)S.d={x:-1,y:0};else if(k.ArrowRight||k.d)S.d={x:1,y:0};else if(k.ArrowUp||k.w)S.d={x:0,y:-1};else if(k.ArrowDown||k.s)S.d={x:0,y:1};let h={x:S.b[0].x+S.d.x,y:S.b[0].y+S.d.y};if(h.x<0||h.x>=W||h.y<0||h.y>=H||S.b.some(p=>p.x===h.x&&p.y===h.y)){lives--;if(lives<=0){initSnake();lives=3}else initSnake();return}S.b.unshift(h);if(h.x===S.f.x&&h.y===S.f.y){score+=10;placeFood()}else S.b.pop();resetGrid();S.b.forEach((p,i)=>setPix(p.x,p.y,i?'#0a8':'#4af'));setPix(S.f.x,S.f.y,'#f44')}
function initInvaders(){I={p:16,b:[],inv:[],dx:1,drop:0,t:0};for(let r=0;r<3;r++)for(let c=0;c<8;c++)I.inv.push({x:4+c*3,y:2+r*2,alive:true})}
function tickInvaders(){I.t++;if(keys.ArrowLeft||keys.a)I.p=Math.max(0,I.p-1);if(keys.ArrowRight||keys.d)I.p=Math.min(W-1,I.p+1);if(keys[' ']&&I.t%3===0)I.b.push({x:I.p,y:H-2,dir:-1});I.b.forEach(b=>b.y+=b.dir);I.b=I.b.filter(b=>b.y>=0&&b.y<H);if(I.t%5===0){let edge=I.inv.some(i=>i.alive&&(i.x<=0&&I.dx<0||i.x>=W-2&&I.dx>0));if(edge){I.dx*=-1;I.inv.forEach(i=>i.y++)}else I.inv.forEach(i=>i.x+=I.dx)}if(I.t%3===0)I.inv.filter(i=>i.alive).forEach(i=>{if(Math.random()<0.08)I.b.push({x:i.x,y:i.y+1,dir:1})});I.b.forEach(b=>{I.inv.forEach(i=>{if(i.alive&&b.x>=i.x&&b.x<=i.x+1&&b.y===i.y){i.alive=false;b.y=-1;score+=10}})});I.b=I.b.filter(b=>b.y>=0);if(I.inv.some(i=>i.alive&&i.y>=H-3)){lives--;initInvaders()}resetGrid();I.inv.filter(i=>i.alive).forEach(i=>{setPix(i.x,i.y,'#4f4');setPix(i.x+1,i.y,'#4f4')});I.b.forEach(b=>setPix(b.x,b.y,'#ff0'));setPix(I.p,H-1,'#4af');setPix(I.p+1,H-1,'#4af')}
function initBreakout(){B={p:16,x:16,y:H-4,vx:1,vy:-1,bricks:[]};for(let r=0;r<3;r++)for(let c=0;c<10;c++)B.bricks.push({x:2+c*3,y:2+r,alive:true})}
function tickBreakout(){if(keys.ArrowLeft||keys.a)B.p=Math.max(0,B.p-2);if(keys.ArrowRight||keys.d)B.p=Math.min(W-2,B.p+2);B.x+=B.vx;B.y+=B.vy;if(B.x<=0||B.x>=W-1)B.vx*=-1;if(B.y<=0)B.vy*=-1;if(B.y>=H-2&&B.x>=B.p&&B.x<=B.p+2){B.vy*=-1;B.vx=(B.x-B.p-1)/2||1}if(B.y>=H){lives--;if(lives<=0){initBreakout();lives=3}else{B.x=16;B.y=H-4;B.vy=-1}}B.bricks.forEach(b=>{if(b.alive&&B.x>=b.x&&B.x<=b.x+2&&B.y===b.y){b.alive=false;B.vy*=-1;score+=10}});resetGrid();B.bricks.filter(b=>b.alive).forEach(b=>{for(let d=0;d<3;d++)setPix(b.x+d,b.y,'#f84')});for(let d=0;d<3;d++)setPix(B.p+d,H-1,'#4af');setPix(Math.floor(B.x),Math.floor(B.y),'#fff')}
function initPong(){P={a:4,b:H/2-2,cpu:W-5,ball:{x:W/2,y:H/2,vx:1,vy:1}}}
function tickPong(){if(keys.ArrowUp||keys.w)P.b=Math.max(0,P.b-1);if(keys.ArrowDown||keys.s)P.b=Math.min(H-3,P.b+1);let b=P.ball;b.x+=b.vx;b.y+=b.vy;if(b.y<=0||b.y>=H-1)b.vy*=-1;if(b.x<=P.a+1&&b.y>=P.b&&b.y<=P.b+2){b.vx*=-1;b.vy=(b.y-P.b-1)/2||1}if(b.x>=W-6){if(b.y>=P.cpu&&b.y<=P.cpu+2){b.vx*=-1;b.vy=(b.y-P.cpu-1)/2||1}else{score+=10;initPong();return}}if(b.x<0){lives--;if(lives<=0){initPong();lives=3}else initPong()}let cy=Math.floor(b.y);P.cpu=Math.max(0,Math.min(H-3,cy-1));resetGrid();for(let d=0;d<3;d++){setPix(P.a,P.b+d,'#4af');setPix(W-5,P.cpu+d,'#f44')}setPix(Math.floor(b.x),Math.floor(b.y),'#fff')}
buildGrids();refresh();
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
        elif self.path == "/api/frame":
            rgb = data.get("rgb", [])
            resp = send_frame(rgb)
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
    print("Device: %s" % DEV, flush=True)
    print("Dashboard: http://0.0.0.0:%d" % PORT, flush=True)
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
