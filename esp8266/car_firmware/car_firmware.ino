// esp8266/car_firmware.ino
// Switch from AP mode to STA mode
// ESP8266 connects to phone hotspot

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <WebSocketsServer.h>

// Phone hotspot credentials
// User creates hotspot with these exact credentials
const char* STA_SSID = "GestureCar-Phone";
const char* STA_PASS = "gesture123";

// Request fixed IP from DHCP
// This makes the IP predictable — always 192.168.43.100 on Android
// or whatever you configure
IPAddress local_IP(192, 168, 43, 100);  // desired fixed IP
IPAddress gateway(192, 168, 43, 1);     // phone hotspot gateway (Android)
IPAddress subnet(255, 255, 255, 0);

ESP8266WebServer http(80);
WebSocketsServer ws(81);

// ── Motor pins ─────────────────────────────────────────────────
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

// ── HTML served from ESP8266 ────────────────────────────────────
// Minimal redirect page — sends user to GitHub Pages
// with the car's IP embedded as a URL parameter
// This way the app knows the car's IP without user typing it
const char REDIRECT_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/>
<title>Gesture RC Car</title>
<style>
body{font-family:sans-serif;background:#0f1117;color:#e8eaf0;
display:flex;flex-direction:column;align-items:center;
justify-content:center;min-height:100vh;gap:20px;padding:20px;text-align:center;}
h1{font-size:22px;}p{color:#6b7080;line-height:1.8;}
.btn{background:#00e676;border:none;border-radius:12px;
padding:16px 32px;color:#000;font-size:16px;font-weight:800;
cursor:pointer;text-decoration:none;display:inline-block;}
code{background:#1a1d27;padding:3px 10px;border-radius:6px;
font-size:14px;color:#4dabf7;}
</style>
</head>
<body>
<h1>⬡ Gesture RC Car</h1>
<p>Car is online.<br>Opening control app...</p>
<script>
// Redirect to GitHub Pages with car IP as parameter
const carIP = location.hostname;
const appURL = 'https://yash-patil-26.github.io/Gesture_Car/?car=' + carIP;
setTimeout(() => { window.location.href = appURL; }, 1500);
</script>
<p>If not redirected: <a class="btn" id="link">Open App</a></p>
<script>
document.getElementById('link').href =
  'https://yash-patil-26.github.io/Gesture_Car/?car=' + location.hostname;
</script>
</body>
</html>
)rawliteral";

// ── Motors ──────────────────────────────────────────────────────
void stopMotors() {
  digitalWrite(IN1,LOW);digitalWrite(IN2,LOW);
  digitalWrite(IN3,LOW);digitalWrite(IN4,LOW);
  analogWrite(ENA,0);analogWrite(ENB,0);
}
void drive(bool l1,bool l2,bool r1,bool r2,int spd){
  digitalWrite(IN1,l1);digitalWrite(IN2,l2);
  digitalWrite(IN3,r1);digitalWrite(IN4,r2);
  analogWrite(ENA,spd);analogWrite(ENB,spd);
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

// ── WebSocket ───────────────────────────────────────────────────
void onWsEvent(uint8_t num,WStype_t type,uint8_t* payload,size_t len){
  switch(type){
    case WStype_CONNECTED:
      if(activeClient==-1){
        activeClient=num;lastCmd=millis();
        ws.sendTXT(num,"READY");
        Serial.printf("[WS] Client #%d active\n",num);
      } else {
        ws.sendTXT(num,
          "BUSY:Car already controlled. Ask them to close the app.");
        delay(80); ws.disconnect(num);
      }
      break;
    case WStype_DISCONNECTED:
      if(num==activeClient){
        activeClient=-1;stopMotors();
        Serial.println("[WS] Controller left — stopped");
      }
      break;
    case WStype_TEXT:
      if(num==activeClient) execute(String((char*)payload));
      break;
    default:break;
  }
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

  // Request fixed IP — makes car always findable
  WiFi.config(local_IP, gateway, subnet);
  WiFi.mode(WIFI_STA);
  WiFi.begin(STA_SSID, STA_PASS);

  Serial.print("Connecting to hotspot");
  int tries=0;
  while(WiFi.status()!=WL_CONNECTED && tries<40){
    delay(500);Serial.print(".");tries++;
  }

  if(WiFi.status()==WL_CONNECTED){
    Serial.println("\n✓ Connected");
    Serial.print("Car IP: ");
    Serial.println(WiFi.localIP());
    Serial.println("Open http://"+WiFi.localIP().toString()+" on phone");
  } else {
    Serial.println("\n✗ WiFi failed — check hotspot name/password");
  }

  // HTTP: serve redirect page
  http.on("/",[](){ http.send_P(200,"text/html",REDIRECT_HTML); });
  http.begin();

  ws.begin();
  ws.onEvent(onWsEvent);
  lastCmd=millis();
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