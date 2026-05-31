// Mode B: MQTT client connecting to HiveMQ cloud
// ESP8266 subscribes to command topic
// Receives FORWARD/STOP/LEFT/RIGHT/REVERSE from phone
//
// Libraries needed (Arduino Library Manager):
//   PubSubClient by Nick O'Leary
//   WiFiClientSecure (built into ESP8266 package)

#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>

// ── Your WiFi (any WiFi with internet) ────────────────────────
const char* WIFI_SSID = "Mudron";
const char* WIFI_PASS = "1234567890";

// ── HiveMQ Cloud credentials ───────────────────────────────────
// Replace with your actual cluster details
const char* MQTT_HOST = "29455b01c27447b488b1ec93488ce95d.s1.eu.hivemq.cloud";
const int   MQTT_PORT = 8883;  // TLS port
const char* MQTT_USER = "gesturecar";
const char* MQTT_PASS = "#Yash@2026";
const char* MQTT_ID   = "esp8266_car_01";

// ── Topics ─────────────────────────────────────────────────────
const char* TOPIC_CMD    = "gesture/car/command";
const char* TOPIC_STATUS = "gesture/car/status";

// ── Motor pins ─────────────────────────────────────────────────
#define IN1 D1
#define IN2 D2
#define IN3 D5
#define IN4 D6
#define ENA D7
#define ENB D8
#define SPEED 700

// ── State ──────────────────────────────────────────────────────
unsigned long lastCmd = 0;
const unsigned long WATCHDOG_MS = 1500; // longer for cloud latency
bool carBusy = false;
String activeController = "";

WiFiClientSecure wifiClient;
PubSubClient mqtt(wifiClient);

// ── Motors ─────────────────────────────────────────────────────
void stopMotors() {
  digitalWrite(IN1,LOW); digitalWrite(IN2,LOW);
  digitalWrite(IN3,LOW); digitalWrite(IN4,LOW);
  analogWrite(ENA,0);    analogWrite(ENB,0);
}
void drive(bool l1,bool l2,bool r1,bool r2,int s){
  digitalWrite(IN1,l1); digitalWrite(IN2,l2);
  digitalWrite(IN3,r1); digitalWrite(IN4,r2);
  analogWrite(ENA,s);   analogWrite(ENB,s);
}
void execute(String cmd){
  if      (cmd=="FORWARD") drive(1,0,1,0,SPEED);
  else if (cmd=="REVERSE") drive(0,1,0,1,SPEED);
  else if (cmd=="LEFT")    drive(0,1,1,0,SPEED);
  else if (cmd=="RIGHT")   drive(1,0,0,1,SPEED);
  else                     stopMotors();
  lastCmd = millis();
}

// ── MQTT message handler ───────────────────────────────────────
void onMessage(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (int i = 0; i < length; i++) msg += (char)payload[i];
  msg.trim();

  String t = String(topic);

  if (t == TOPIC_CMD) {
    // Format: "CONTROLLER_ID:COMMAND"
    // e.g. "phone_abc123:FORWARD"
    int sep = msg.indexOf(':');
    if (sep == -1) return;

    String controller = msg.substring(0, sep);
    String command    = msg.substring(sep + 1);
    command.toUpperCase();

    // Single-controller enforcement
    if (command == "CONNECT") {
      if (activeController == "" || activeController == controller) {
        activeController = controller;
        lastCmd = millis();
        mqtt.publish(TOPIC_STATUS, ("READY:" + controller).c_str());
        Serial.println("[MQTT] Controller: " + controller);
      } else {
        mqtt.publish(TOPIC_STATUS, "BUSY:Car already controlled");
        Serial.println("[MQTT] Rejected: " + controller);
      }
      return;
    }

    if (command == "DISCONNECT") {
      if (activeController == controller) {
        activeController = "";
        stopMotors();
        mqtt.publish(TOPIC_STATUS, "FREE");
        Serial.println("[MQTT] Released by: " + controller);
      }
      return;
    }

    // Only accept commands from active controller
    if (activeController == controller) {
      execute(command);
    }
  }
}

// ── MQTT connect/reconnect ─────────────────────────────────────
void connectMQTT() {
  wifiClient.setInsecure(); // Skip cert verification for simplicity
  // For production: wifiClient.setFingerprint(HIVEMQ_FINGERPRINT);

  Serial.print("Connecting to MQTT broker");
  int attempts = 0;
  while (!mqtt.connected() && attempts < 10) {
    if (mqtt.connect(MQTT_ID, MQTT_USER, MQTT_PASS)) {
      Serial.println("\n✓ MQTT connected");
      mqtt.subscribe(TOPIC_CMD);
      mqtt.publish(TOPIC_STATUS, "ONLINE");
      Serial.println("Subscribed to: " + String(TOPIC_CMD));
    } else {
      Serial.print(".");
      delay(3000);
      attempts++;
    }
  }
}

// ── Setup ──────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(100);

  pinMode(IN1,OUTPUT); digitalWrite(IN1,LOW);
  pinMode(IN2,OUTPUT); digitalWrite(IN2,LOW);
  pinMode(IN3,OUTPUT); digitalWrite(IN3,LOW);
  pinMode(IN4,OUTPUT); digitalWrite(IN4,LOW);
  pinMode(ENA,OUTPUT); analogWrite(ENA,0);
  pinMode(ENB,OUTPUT); analogWrite(ENB,0);

  // Connect WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\n✓ WiFi connected: " + WiFi.localIP().toString());

  // REPLACE WITH THIS (add setBufferSize BEFORE setServer):
  mqtt.setBufferSize(1024);  // ← THIS LINE FIXES THE DOTS PROBLEM
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setKeepAlive(30);
  connectMQTT();

  lastCmd = millis();
  Serial.println("Car ready. Waiting for commands via MQTT.");
}

// ── Loop ───────────────────────────────────────────────────────
void loop() {
  // Maintain MQTT connection
  if (!mqtt.connected()) {
    connectMQTT();
  }
  mqtt.loop();

  // Watchdog — stop if no command recently
  if (activeController != "" &&
      millis() - lastCmd > WATCHDOG_MS) {
    stopMotors();
    lastCmd = millis();
  }

  yield();
}