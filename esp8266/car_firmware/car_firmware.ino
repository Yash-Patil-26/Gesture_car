// Complete rewrite — self-contained HTTP + WebSocket
// Phone opens http://[car-ip] directly
// No HTTPS context = no mixed content block
// model.onnx fetched from GitHub Pages on first load only

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <WebSocketsServer.h>

// ── Phone hotspot ──────────────────────────────────────────────
// Set these to match YOUR phone hotspot exactly
const char* SSID = "SuperCar";     // exact name, case sensitive
const char* PASS = "1234567890"; // exact password

// GitHub Pages base URL for fetching model.onnx
// Update this to your actual URL
const char* GITHUB_PAGES = "https://yash-patil-26.github.io/Gesture_Car";

ESP8266WebServer http(80);
WebSocketsServer ws(81);

#define IN1  D1
#define IN2  D2
#define IN3  D5
#define IN4  D6
#define ENA  D7
#define ENB  D8
#define SPEED 700

int  activeClient = -1;
unsigned long lastCmd = 0;
const unsigned long WATCHDOG_MS = 600;

// ── Complete control app HTML ───────────────────────────────────
// Served over HTTP from ESP8266
// ws:// connection allowed because page itself is HTTP
// model.onnx fetched from GitHub Pages (CORS allowed)

const char APP_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"/>
<title>Gesture RC Car</title>
<style>
:root{
  --bg:#0f1117;--surface:#1a1d27;--border:#2a2d3a;
  --text:#e8eaf0;--muted:#6b7080;
  --green:#00e676;--blue:#4dabf7;--amber:#ffb300;
  --red:#ff5252;--purple:#b39ddb;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Segoe UI',system-ui,sans-serif;
  background:var(--bg);color:var(--text);
  min-height:100dvh;display:flex;flex-direction:column;
  -webkit-tap-highlight-color:transparent;}
.overlay{position:fixed;inset:0;background:rgba(15,17,23,.97);
  display:flex;flex-direction:column;align-items:center;
  justify-content:center;z-index:999;padding:24px;
  text-align:center;gap:16px;}
.overlay.gone{display:none;}
.spinner{width:48px;height:48px;border:3px solid var(--border);
  border-top-color:var(--green);border-radius:50%;
  animation:spin 1s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}
.overlay h2{font-size:22px;font-weight:800;}
.overlay p{font-size:14px;color:var(--muted);
  line-height:1.8;max-width:320px;}
#busy-overlay h2{color:var(--amber);}
.btn{background:var(--green);border:none;border-radius:12px;
  padding:14px 28px;color:#000;font-size:15px;font-weight:800;
  cursor:pointer;width:100%;max-width:320px;}
.btn:active{transform:scale(.97);}
header{background:var(--surface);border-bottom:1px solid var(--border);
  padding:11px 16px;display:flex;justify-content:space-between;
  align-items:center;position:sticky;top:0;z-index:100;}
header h1{font-size:16px;font-weight:700;}
.pills{display:flex;gap:6px;}
.pill{font-size:11px;padding:4px 10px;border-radius:20px;
  border:1px solid var(--border);color:var(--muted);
  background:var(--bg);transition:all .25s;white-space:nowrap;}
.pill.on{color:var(--green);border-color:var(--green);}
.pill.err{color:var(--red);border-color:var(--red);}
main{flex:1;display:flex;flex-direction:column;gap:12px;padding:12px;}
.cam-wrap{position:relative;background:#000;border-radius:12px;
  overflow:hidden;aspect-ratio:4/3;}
#c{width:100%;height:100%;object-fit:cover;display:block;transform:scaleX(-1);}
.hud{position:absolute;inset:0;display:flex;flex-direction:column;
  justify-content:space-between;padding:10px;pointer-events:none;}
.hud-top{display:flex;justify-content:space-between;}
.gbadge{background:rgba(0,0,0,.75);padding:5px 13px;
  border-radius:20px;font-size:14px;font-weight:600;color:var(--green);}
.fps{background:rgba(0,0,0,.6);padding:3px 8px;
  border-radius:6px;font-size:11px;color:var(--muted);}
.crow{display:flex;align-items:center;gap:8px;}
.ctrack{flex:1;height:5px;background:rgba(255,255,255,.15);
  border-radius:3px;overflow:hidden;}
.cfill{height:100%;border-radius:3px;
  background:var(--green);width:0;transition:width .12s;}
.cpct{font-size:11px;color:var(--muted);min-width:30px;text-align:right;}
.card{background:var(--surface);border:1px solid var(--border);
  border-radius:12px;padding:14px;}
.lbl{font-size:11px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.8px;margin-bottom:10px;}
.cmd{font-size:54px;font-weight:900;letter-spacing:3px;
  text-align:center;padding:8px 0;color:var(--red);transition:color .12s;}
.cmd.FORWARD{color:var(--green);}
.cmd.REVERSE{color:var(--blue);}
.cmd.LEFT{color:var(--purple);}
.cmd.RIGHT{color:var(--amber);}
.dpad{display:flex;flex-direction:column;align-items:center;gap:6px;}
.dr{display:flex;gap:6px;}
.db{width:62px;height:62px;border-radius:10px;
  background:var(--bg);border:1px solid var(--border);
  display:flex;align-items:center;justify-content:center;
  font-size:22px;color:var(--muted);transition:all .1s;}
.db.lit{background:#0d2b1a;border-color:var(--green);
  color:var(--green);box-shadow:0 0 16px rgba(0,230,118,.35);}
.db.lit.s{background:#2a0d0d;border-color:var(--red);
  color:var(--red);box-shadow:0 0 16px rgba(255,82,82,.35);}
.cbar{display:flex;align-items:center;gap:10px;
  padding:9px 12px;background:var(--bg);
  border-radius:8px;border:1px solid var(--border);}
.dot{width:8px;height:8px;border-radius:50%;
  background:var(--muted);flex-shrink:0;}
.dot.on{background:var(--green);box-shadow:0 0 6px var(--green);}
.dot.err{background:var(--red);}
.ctxt{flex:1;font-size:12px;color:var(--muted);}
.sbtn{background:var(--green);border:none;border-radius:12px;
  padding:17px;color:#000;font-size:17px;font-weight:800;
  width:100%;cursor:pointer;transition:all .15s;}
.sbtn.run{background:var(--red);color:#fff;}
.sbtn:active{transform:scale(.97);}
@media(min-width:580px){
  main{flex-direction:row;flex-wrap:wrap;}
  .cam-wrap{max-width:380px;}
  .r{flex:1;display:flex;flex-direction:column;gap:12px;min-width:260px;}
}
</style>
</head>
<body>

<div class="overlay" id="lo">
  <div class="spinner"></div>
  <h2>Gesture RC Car</h2>
  <p id="lt">Loading ML model&hellip;<br>
    <small>Fetching from cloud &middot; ~15s first time</small></p>
</div>

<div class="overlay gone" id="bo">
  <div style="font-size:52px">&#x1F512;</div>
  <h2>Car Busy</h2>
  <p>Already controlled by another device.<br>
     Ask them to close the app, then retry.</p>
  <button class="btn" id="br">&#x21BA; Try Again</button>
</div>

<header>
  <h1>&#x2B21; Gesture RC Car</h1>
  <div class="pills">
    <span class="pill" id="pc">&#9679; Cam</span>
    <span class="pill" id="pm">&#9679; ML</span>
    <span class="pill" id="pw">&#9679; Car</span>
  </div>
</header>

<main>
  <div class="cam-wrap">
    <canvas id="c"></canvas>
    <div class="hud">
      <div class="hud-top">
        <div class="gbadge" id="gb">&mdash;</div>
        <div class="fps" id="fp">0 fps</div>
      </div>
      <div class="crow">
        <div class="ctrack"><div class="cfill" id="cf"></div></div>
        <span class="cpct" id="cp">0%</span>
      </div>
    </div>
  </div>

  <div class="r">
    <div class="card">
      <div class="lbl">Active Command</div>
      <div class="cmd STOP" id="cd">STOP</div>
    </div>
    <div class="card">
      <div class="dpad">
        <div class="db" id="dF">&#9650;</div>
        <div class="dr">
          <div class="db" id="dL">&#9664;</div>
          <div class="db s" id="dS">&#9632;</div>
          <div class="db" id="dR">&#9654;</div>
        </div>
        <div class="db" id="dV">&#9660;</div>
      </div>
    </div>
    <div class="card">
      <div class="lbl">Connection</div>
      <div class="cbar">
        <div class="dot on" id="wd"></div>
        <span class="ctxt" id="wt">Connected to car</span>
      </div>
    </div>
    <button class="sbtn" id="sb">&#9654; Start Gesture Control</button>
  </div>
</main>

<script src="https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/onnxruntime-web/dist/ort.min.js" crossorigin="anonymous"></script>
<script>
// ── KEY DIFFERENCE ──────────────────────────────────────────────
// This page is served from http://[car-ip] (HTTP, not HTTPS)
// So ws:// WebSocket connections are allowed — no mixed content
// WebSocket connects to same host this page was served from
const CAR_WS = 'ws://' + location.hostname + ':81';

// Model fetched from GitHub Pages (CORS is fine from HTTP origin)
const MODEL_URL  = 'GITHUB_PAGES_PLACEHOLDER/model.onnx';
const LABELS_URL = 'GITHUB_PAGES_PLACEHOLDER/labels.json';

const CONF=.85, VOTES=3;
let sess,lbls=[],ws,running=false,busy=false;
let vbuf=[],last='STOP',lc=null,ls=0;
let fc=0,fv=0,ft=performance.now();
let cam,hds,rt,rn=0;

const cv=document.getElementById('c'),ctx=cv.getContext('2d');
const gb=document.getElementById('gb'),fp=document.getElementById('fp');
const cf=document.getElementById('cf'),cp=document.getElementById('cp');
const cd=document.getElementById('cd');
const wd=document.getElementById('wd'),wt=document.getElementById('wt');
const sb=document.getElementById('sb');
const pc=document.getElementById('pc'),pm=document.getElementById('pm'),pw=document.getElementById('pw');
const D={FORWARD:document.getElementById('dF'),REVERSE:document.getElementById('dV'),
  LEFT:document.getElementById('dL'),RIGHT:document.getElementById('dR'),
  STOP:document.getElementById('dS')};

// Overlays
const hide=id=>document.getElementById(id).classList.add('gone');
const show=id=>document.getElementById(id).classList.remove('gone');
document.getElementById('br').addEventListener('click',()=>{
  busy=false;hide('bo');rn=0;connect();});

// Connection — connects to car WebSocket
// Page is HTTP so ws:// is allowed
function setConn(ok,msg){
  wd.className='dot'+(ok?ok==='on'?' on':' err':'');
  wt.textContent=msg;
  pw.className='pill'+(ok==='on'?' on':ok==='err'?' err':'');
}

function connect(){
  if(busy)return;
  if(rt){clearTimeout(rt);rt=null;}
  if(ws){try{ws.close();}catch(_){}ws=null;}
  setConn('','Connecting to car…');
  try{ws=new WebSocket(CAR_WS);}catch(e){retry();return;}
  ws.onopen=()=>{rn=0;setConn('on','Car connected ✓');};
  ws.onclose=()=>{if(!busy){setConn('err','Reconnecting…');retry();}};
  ws.onerror=()=>setConn('err','Connection error');
  ws.onmessage=e=>{
    if(e.data.startsWith('BUSY:')){
      busy=true;try{ws.close();}catch(_){}
      setConn('err','Car busy');show('bo');
    }
  };
}
function retry(){rn++;rt=setTimeout(connect,Math.min(2000*rn,10000));}

function send(cmd){
  const n=Date.now();
  if((cmd!==lc||n-ls>300)&&ws?.readyState===1){
    ws.send(cmd);lc=cmd;ls=n;
  }
}

function cleanup(){
  if(ws?.readyState===1){ws.send('STOP');ws.close(1000);}
  cam?.stop();
}
window.addEventListener('beforeunload',cleanup);
window.addEventListener('pagehide',cleanup);
document.addEventListener('visibilitychange',
  ()=>{if(document.hidden&&running)send('STOP');});

function vote(l,c,h){
  if(!h||c<CONF){vbuf=[];last='STOP';return 'STOP';}
  const cmd=l.toUpperCase();
  if(cmd==='STOP'){vbuf=[];last='STOP';return 'STOP';}
  vbuf.push(cmd);if(vbuf.length>VOTES)vbuf.shift();
  if(vbuf.length>=VOTES&&vbuf.every(v=>v===vbuf[0]))last=vbuf[0];
  return last;
}

function feat(lms){
  const wx=lms[0].x,wy=lms[0].y,wz=lms[0].z,a=[];
  for(const l of lms)a.push(l.x-wx,l.y-wy,l.z-wz);
  const mx=Math.max(...a.map(Math.abs));
  return mx<1e-6?null:new Float32Array(a.map(v=>v/mx));
}

async function classify(f){
  if(!sess)return null;
  try{
    const t=new ort.Tensor('float32',f,[1,63]);
    const r=await sess.run({float_input:t});
    const p=r['probabilities']?.data
         ||r[Object.keys(r).find(k=>k.toLowerCase().includes('prob'))]?.data;
    if(!p)return null;
    let mi=0,mp=0;p.forEach((v,i)=>{if(v>mp){mp=v;mi=i;}});
    return{label:lbls[mi]||'?',conf:mp};
  }catch{return null;}
}

const CN=[[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],
  [0,9],[9,10],[10,11],[11,12],[0,13],[13,14],[14,15],[15,16],
  [0,17],[17,18],[18,19],[19,20],[5,9],[9,13],[13,17]];
const TI=new Set([4,8,12,16,20]);

function drawL(lms){
  const w=cv.width,h=cv.height;
  ctx.strokeStyle='rgba(255,255,255,.45)';ctx.lineWidth=1.5;
  for(const[a,b]of CN){
    ctx.beginPath();
    ctx.moveTo(lms[a].x*w,lms[a].y*h);
    ctx.lineTo(lms[b].x*w,lms[b].y*h);
    ctx.stroke();
  }
  lms.forEach((l,i)=>{
    ctx.beginPath();
    ctx.arc(l.x*w,l.y*h,i===0?6:TI.has(i)?5:3,0,Math.PI*2);
    ctx.fillStyle=i===0?'#ffb300':TI.has(i)?'#00e676':'#4dabf7';
    ctx.fill();
  });
}

async function onRes(res){
  cv.width=res.image.width;cv.height=res.image.height;
  ctx.clearRect(0,0,cv.width,cv.height);
  ctx.drawImage(res.image,0,0);
  let g='No hand',c=0,h=false;
  if(res.multiHandLandmarks?.length){
    const lms=res.multiHandLandmarks[0];
    h=true;drawL(lms);
    const f=feat(lms);
    if(f){const r=await classify(f);if(r){g=r.label;c=r.conf;}}
  }
  const cmd=vote(g,c,h);
  gb.textContent=g;
  const p=Math.round(c*100);
  cf.style.width=p+'%';cf.style.background=p>=85?'#00e676':'#4dabf7';
  cp.textContent=p+'%';
  cd.textContent=cmd;cd.className='cmd '+cmd;
  Object.entries(D).forEach(([k,el])=>el.classList.toggle('lit',k===cmd));
  fc++;const n=performance.now();
  if(n-ft>=1000){fv=fc;fc=0;ft=n;fp.textContent=fv+' fps';}
  if(running)send(cmd);
}

async function startCam(){
  if(!hds){
    hds=new Hands({locateFile:f=>
      `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${f}`});
    hds.setOptions({maxNumHands:1,modelComplexity:1,
      minDetectionConfidence:.7,minTrackingConfidence:.6});
    hds.onResults(onRes);
  }
  try{
    const s=await navigator.mediaDevices.getUserMedia(
      {video:{facingMode:'user',width:{ideal:640},height:{ideal:480}}});
    const v=document.createElement('video');v.srcObject=s;
    cam=new Camera(v,{onFrame:async()=>{await hds.send({image:v});},
      width:640,height:480});
    await cam.start();pc.classList.add('on');
  }catch{pc.classList.add('err');
    alert('Camera denied — allow camera and reload.');}
}

sb.addEventListener('click',async()=>{
  if(!running){
    running=true;sb.textContent='&#9209; Stop';sb.classList.add('run');
    await startCam();
  }else{
    running=false;sb.textContent='&#9654; Start Gesture Control';
    sb.classList.remove('run');send('STOP');cam?.stop();cam=null;
    cd.textContent='STOP';cd.className='cmd STOP';
    Object.values(D).forEach(e=>e.classList.remove('lit'));
  }
});

// Load model from GitHub Pages
async function loadModel(){
  const lt=document.getElementById('lt');
  try{
    lt.innerHTML='Downloading ML model&hellip;<br><small>Fetching from cloud</small>';
    sess=await ort.InferenceSession.create(MODEL_URL,
      {executionProviders:['wasm']});
    lt.innerHTML='Loading labels&hellip;';
    lbls=(await(await fetch(LABELS_URL)).json()).labels;
    hide('lo');pm.classList.add('on');
    connect();
  }catch(e){
    lt.innerHTML='Load failed.<br><small>'+e.message+'</small>';
    pm.classList.add('err');
  }
}
loadModel();
</script>
</body>
</html>
)rawliteral";

// ── Motor functions ─────────────────────────────────────────────
void stopMotors(){
  digitalWrite(IN1,LOW);digitalWrite(IN2,LOW);
  digitalWrite(IN3,LOW);digitalWrite(IN4,LOW);
  analogWrite(ENA,0);analogWrite(ENB,0);
}
void drive(bool l1,bool l2,bool r1,bool r2,int s){
  digitalWrite(IN1,l1);digitalWrite(IN2,l2);
  digitalWrite(IN3,r1);digitalWrite(IN4,r2);
  analogWrite(ENA,s);analogWrite(ENB,s);
}
void execute(String cmd){
  cmd.trim();cmd.toUpperCase();
  if      (cmd=="FORWARD") drive(1,0,1,0,SPEED);
  else if (cmd=="REVERSE") drive(0,1,0,1,SPEED);
  else if (cmd=="LEFT")    drive(0,1,1,0,SPEED);
  else if (cmd=="RIGHT")   drive(1,0,0,1,SPEED);
  else                     stopMotors();
  lastCmd=millis();
}

// ── WebSocket handler ───────────────────────────────────────────
void onWsEvent(uint8_t num,WStype_t type,uint8_t* p,size_t l){
  switch(type){
    case WStype_CONNECTED:
      if(activeClient==-1){
        activeClient=num;lastCmd=millis();
        ws.sendTXT(num,"READY");
        Serial.printf("[WS] Client #%d active\n",num);
      }else{
        ws.sendTXT(num,"BUSY:Already controlled. Close other app first.");
        delay(80);ws.disconnect(num);
      }
      break;
    case WStype_DISCONNECTED:
      if(num==activeClient){activeClient=-1;stopMotors();
        Serial.println("[WS] Stopped");}
      break;
    case WStype_TEXT:
      if(num==activeClient)execute(String((char*)p));
      break;
    default:break;
  }
}

// ── Build HTML with real GitHub Pages URL ───────────────────────
String buildHTML(){
  String h=String(APP_HTML);
  h.replace("GITHUB_PAGES_PLACEHOLDER",String(GITHUB_PAGES));
  return h;
}

// ── Setup ───────────────────────────────────────────────────────
void setup(){
  Serial.begin(115200);delay(100);
  pinMode(IN1,OUTPUT);digitalWrite(IN1,LOW);
  pinMode(IN2,OUTPUT);digitalWrite(IN2,LOW);
  pinMode(IN3,OUTPUT);digitalWrite(IN3,LOW);
  pinMode(IN4,OUTPUT);digitalWrite(IN4,LOW);
  pinMode(ENA,OUTPUT);analogWrite(ENA,0);
  pinMode(ENB,OUTPUT);analogWrite(ENB,0);

  WiFi.mode(WIFI_STA);
  WiFi.begin(SSID,PASS);
  Serial.print("Connecting");
  int t=0;
  while(WiFi.status()!=WL_CONNECTED&&t<40){
    delay(500);Serial.print(".");t++;
  }
  if(WiFi.status()==WL_CONNECTED){
    Serial.println("\n✓ Connected");
    Serial.print("Car IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("Open in phone browser: http://");
    Serial.println(WiFi.localIP());
  }else{
    Serial.println("\n✗ WiFi failed");
    Serial.println("Check SSID and password in firmware");
  }

  // Serve control app at root
  http.on("/",[](){ http.send(200,"text/html",buildHTML()); });
  http.on("/favicon.ico",[](){ http.send(204); });
  http.begin();

  ws.begin();
  ws.onEvent(onWsEvent);
  lastCmd=millis();

  Serial.println("HTTP server on port 80");
  Serial.println("WebSocket server on port 81");
}

// ── Loop ────────────────────────────────────────────────────────
void loop(){
  http.handleClient();
  ws.loop();
  if(activeClient!=-1&&millis()-lastCmd>WATCHDOG_MS){
    stopMotors();lastCmd=millis();
  }
  yield();
}