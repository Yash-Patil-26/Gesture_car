# Gesture RC Car

Control a real RC car with hand gestures using computer vision
and machine learning. Two control modes — laptop or phone.

**Live demo page →** `https://yash-patil-26.github.io/Gesture_Car/`

---

## Control Modes

### Mode A — Laptop controls car (local)
Laptop webcam → MediaPipe → Random Forest → Flask → ESP8266 → motors
Laptop and car must be on the same WiFi network.
Run `python src/app.py` on laptop. Open `http://localhost:5000`.

### Mode B — Phone controls car (anywhere via cloud)
Phone camera → MediaPipe.js → ONNX model → MQTT → HiveMQ cloud
↓
ESP8266 → motors
Works from anywhere with internet. Car needs any WiFi with internet.
Open `https://yash-patil-26.github.io/Gesture_Car/` on phone.

---

## Demo — Mode B (Phone)

| Step | Action |
|---|---|
| 1 | Power on car — ESP8266 connects to WiFi and HiveMQ broker |
| 2 | Open `https://yash-patil-26.github.io/Gesture_Car/` on phone |
| 3 | Wait ~15s for ML model to load (cached permanently after) |
| 4 | Green pills appear: Cam · ML · Broker · Car |
| 5 | Tap Start → show hand to front camera |
| 6 | Car moves. Close tab → car stops automatically. |

---

## Gestures

| Gesture | Command |
|---|---|
| Open palm facing camera | FORWARD |
| Closed fist | STOP |
| Index finger pointing left | LEFT |
| Index finger pointing right | RIGHT |
| Thumbs down | REVERSE |

---

## Hardware

| Component | Detail |
|---|---|
| ESP8266 NodeMCU | WiFi + MQTT client + motor control |
| L298N motor driver | Drives 4 TT motors |
| 2× 18650 battery (7.4V series) | Power supply |
| 4× TT motors + 65mm wheels | Movement |
| Acrylic chassis (200×160mm) | Structure |
| SPST switch | Master power |

### Pin Mapping

| NodeMCU | GPIO | L298N | Function |
|---|---|---|---|
| D1 | GPIO5 | IN1 | Left forward |
| D2 | GPIO4 | IN2 | Left reverse |
| D5 | GPIO14 | IN3 | Right forward |
| D6 | GPIO12 | IN4 | Right reverse |
| D7 | GPIO13 | ENA | Left speed PWM |
| D8 | GPIO15 | ENB | Right speed PWM |
| VIN | — | 5V out | Power from L298N |
| GND | — | GND | Common ground |

---

## Software Setup

### Prerequisites
- Python 3.9–3.11
- Arduino IDE with ESP8266 board package
- HiveMQ Cloud free account (for Mode B)

### Install Python dependencies
```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
```

### Training pipeline (run once)
```bash
# Collect webcam gesture samples
python src/collect_data.py

# Train Random Forest classifier
python src/train_model.py

# Export to ONNX for browser inference
python src/export_model.py

# Run local dashboard (Mode A)
python src/app.py
```

---

## ESP8266 Firmware Setup

### Required Arduino libraries
- WebSockets by Markus Sattler
- PubSubClient by Nick O'Leary

### Configuration (update before flashing)
```cpp
// WiFi credentials
const char* WIFI_SSID = "YourWiFiName";
const char* WIFI_PASS = "YourWiFiPassword";

// HiveMQ Cloud (get free at console.hivemq.cloud)
const char* MQTT_HOST = "xxxxxxxx.s1.eu.hivemq.cloud";
const char* MQTT_PASS = "YourMQTTPassword";
```

### Flash steps
1. Open `esp8266/car_firmware.ino` in Arduino IDE
2. Update credentials above
3. Tools → Board → `NodeMCU 1.0 (ESP-12E Module)`
4. Upload
5. Open Serial Monitor at 115200 baud — confirm connected

---

## ML Model Details

| Property | Value |
|---|---|
| Algorithm | Random Forest (100 trees) |
| Input | 63 features (21 landmarks × x,y,z normalized) |
| Classes | 5 (forward, reverse, left, right, stop) |
| CV accuracy | 97–99% |
| Inference | <1ms Python · ~5ms ONNX browser |
| Cloud latency | ~50–100ms via MQTT |

---

## Architecture
Training (laptop, done once):
Images → filter → extract landmarks → CSV → Random Forest → ONNX
Mode A runtime:
Laptop cam → MediaPipe → RF (Python) → WebSocket → ESP8266
Mode B runtime:
Phone cam → MediaPipe.js → ONNX (browser) → MQTT WSS
↓
HiveMQ cloud broker
↓
ESP8266 MQTT client → L298N → motors

---

## Project Structure
gesture-car/
├── esp8266/
│   ├── car_firmware.ino     # ESP8266 — MQTT client + motors
│   └── pin_reference.md
├── src/
│   ├── config.py            # All constants
│   ├── hand_utils.py        # MediaPipe + FastVoteBuffer
│   ├── collect_data.py      # Webcam data collection
│   ├── filter_images.py     # Image quality filter (one-time)
│   ├── extract_from_images.py
│   ├── train_model.py       # Train Random Forest
│   ├── export_model.py      # Export to ONNX
│   └── app.py               # Mode A local dashboard
├── docs/
│   ├── index.html           # Mode B phone control app
│   ├── model.onnx           # Trained model for browser
│   ├── labels.json          # Gesture class labels
│   ├── sw.js                # PWA service worker
│   └── manifest.json        # PWA manifest
├── templates/               # Mode A local dashboard UI
├── static/                  # Mode A CSS + JS
├── outputs/
│   └── confusion_matrix.png
├── .gitignore
├── README.md
└── requirements.txt

---

## License
MIT