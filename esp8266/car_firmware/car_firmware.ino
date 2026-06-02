// ─────────────────────────────────────────────────────────────
// ESP8266 connects to WiFi → subscribes to HiveMQ MQTT topic
// Receives gesture commands → drives L298N motors
//
// Required libraries (Arduino Library Manager):
//   PubSubClient  by Nick O'Leary  (version 2.8)
//   ESP8266WiFi   (built into ESP8266 board package)
// ─────────────────────────────────────────────────────────────

#include <ESP8266WiFi.h>
#include <WiFiClientSecureBearSSL.h>
#include <PubSubClient.h>

// ── WiFi credentials ────────────────────────────────────────────
// Any WiFi with internet access works here
// Home WiFi, office WiFi, phone hotspot — all fine
const char* WIFI_SSID = "MudrOn";
const char* WIFI_PASS = "1234567890";

// ── HiveMQ Cloud credentials ────────────────────────────────────
// Replace with YOUR cluster URL from HiveMQ console
// Format: xxxxxxxxxxxxxxxx.s1.eu.hivemq.cloud
const char* MQTT_BROKER  = "29455b01c27447b488b1ec93488ce95d.s1.eu.hivemq.cloud";
const int   MQTT_PORT    = 8883;
const char* MQTT_USER    = "Mudron";
const char* MQTT_PASS    = "26crGesture";
const char* MQTT_CLIENT  = "gesture_car_esp8266";

// ── MQTT topics ─────────────────────────────────────────────────
const char* TOPIC_CMD    = "gesturecar/command";
const char* TOPIC_STATUS = "gesturecar/status";

// ── Motor pins ──────────────────────────────────────────────────
#define IN1   D1
#define IN2   D2
#define IN3   D5
#define IN4   D6
#define ENA   D7
#define ENB   D8
#define SPEED 700    // 0–1023 (10-bit PWM)

// ── Watchdog and ping timers ────────────────────────────────────
unsigned long lastCmd  = 0;
unsigned long lastPing = 0;
const unsigned long WATCHDOG_MS = 1500;  // longer for cloud latency
const unsigned long PING_MS     = 5000;  // status publish interval

// ── MQTT over TLS ───────────────────────────────────────────────
BearSSL::WiFiClientSecure net;
PubSubClient mqtt(net);

// ── Motor control ────────────────────────────────────────────────
void stopMotors() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  analogWrite(ENA, 0);    analogWrite(ENB, 0);
}

void drive(bool l1, bool l2, bool r1, bool r2, int spd) {
  digitalWrite(IN1, l1); digitalWrite(IN2, l2);
  digitalWrite(IN3, r1); digitalWrite(IN4, r2);
  analogWrite(ENA, spd); analogWrite(ENB, spd);
}

void execute(String cmd) {
  cmd.trim(); cmd.toUpperCase();

  // Ignore heartbeat pings from app
  if (cmd == "PING") return;

  if      (cmd == "FORWARD") drive(1, 0, 1, 0, SPEED);
  else if (cmd == "REVERSE") drive(0, 1, 0, 1, SPEED);
  else if (cmd == "LEFT")    drive(0, 1, 1, 0, SPEED);
  else if (cmd == "RIGHT")   drive(1, 0, 0, 1, SPEED);
  else                       stopMotors();

  lastCmd = millis();
  Serial.printf("[CMD] %s\n", cmd.c_str());
}

// ── MQTT message callback ────────────────────────────────────────
void onMessage(char* topic, byte* payload, unsigned int len) {
  String msg;
  for (unsigned int i = 0; i < len; i++) {
    msg += (char)payload[i];
  }
  Serial.printf("[MQTT] topic=%s msg=%s\n", topic, msg.c_str());
  execute(msg);
}

// ── WiFi connect ─────────────────────────────────────────────────
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("[WIFI] Connecting");
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(500);
    Serial.print(".");
    tries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WIFI] Connected — IP: %s\n",
      WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WIFI] Failed — will retry in loop");
  }
}

// ── MQTT connect ─────────────────────────────────────────────────
void connectMQTT() {
  // setInsecure skips certificate validation
  // Acceptable for this project — HiveMQ uses valid certs
  net.setInsecure();

  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setKeepAlive(30);
  mqtt.setBufferSize(512);

  Serial.print("[MQTT] Connecting to HiveMQ");
  int tries = 0;
  while (!mqtt.connected() && tries < 5) {
    if (mqtt.connect(MQTT_CLIENT, MQTT_USER, MQTT_PASS)) {
      Serial.println("\n[MQTT] Connected ✓");
      mqtt.subscribe(TOPIC_CMD);
      mqtt.publish(TOPIC_STATUS, "ONLINE");
      Serial.printf("[MQTT] Subscribed to: %s\n", TOPIC_CMD);
    } else {
      Serial.printf(" rc=%d", mqtt.state());
      delay(3000);
      tries++;
    }
  }
  if (!mqtt.connected()) {
    Serial.println("\n[MQTT] Failed after 5 tries — will retry in loop");
  }
}

// ── Setup ─────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(100);

  // Motor pins — all LOW on boot
  pinMode(IN1, OUTPUT); digitalWrite(IN1, LOW);
  pinMode(IN2, OUTPUT); digitalWrite(IN2, LOW);
  pinMode(IN3, OUTPUT); digitalWrite(IN3, LOW);
  pinMode(IN4, OUTPUT); digitalWrite(IN4, LOW);
  pinMode(ENA, OUTPUT); analogWrite(ENA, 0);
  pinMode(ENB, OUTPUT); analogWrite(ENB, 0);

  Serial.println("\n══════════════════════════════════");
  Serial.println("  Gesture RC Car — Booting");
  Serial.printf ("  WiFi   : %s\n", WIFI_SSID);
  Serial.printf ("  Broker : %s\n", MQTT_BROKER);
  Serial.printf ("  Topic  : %s\n", TOPIC_CMD);
  Serial.println("══════════════════════════════════");

  connectWiFi();

  if (WiFi.status() == WL_CONNECTED) {
    connectMQTT();
  }

  lastCmd  = millis();
  lastPing = millis();
}

// ── Loop ──────────────────────────────────────────────────────────
void loop() {
  // Reconnect WiFi if dropped
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] Lost — reconnecting");
    connectWiFi();
  }

  // Reconnect MQTT if dropped
  if (WiFi.status() == WL_CONNECTED && !mqtt.connected()) {
    Serial.println("[MQTT] Lost — reconnecting");
    connectMQTT();
  }

  // Process incoming MQTT messages
  if (mqtt.connected()) {
    mqtt.loop();
  }

  // Watchdog — stop motors if no command received recently
  // Handles: app closed, internet dropped, phone locked
  if (millis() - lastCmd > WATCHDOG_MS) {
    stopMotors();
    lastCmd = millis();
  }

  // Periodic status ping — lets app know car is alive
  if (mqtt.connected() && millis() - lastPing > PING_MS) {
    mqtt.publish(TOPIC_STATUS, "ALIVE");
    lastPing = millis();
  }

  yield();
}