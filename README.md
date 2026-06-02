# Gesture RC Car

Control a real RC car with hand gestures using your phone.
No apps. No wearables. No laptop during demo.

**Live demo →** `https://yash-patil-26.github.io/Gesture_Car/`

---

## How It Works
Phone camera → MediaPipe.js (hand landmarks)
→ ONNX Random Forest (gesture classification)
→ HiveMQ MQTT wss:// (cloud relay)
→ ESP8266 (motor commands)
→ L298N → 4 TT motors → car moves

All ML inference runs in the browser.
Commands travel through HiveMQ cloud MQTT broker.
No local network required — works over any internet connection.

---

## Demo — Anyone Can Use This

Power on car
ESP8266 connects to WiFi automatically
Open on any phone with internet:
https://yash-patil-26.github.io/Gesture_Car/
Wait ~15s for ML model to load
Green "Car" pill appears when car is online
Tap Start → allow camera → show hand → car moves
Close tab → car stops automatically


No IP address. No hotspot setup. No laptop needed.

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
| VIN | — | 5V out | Logic power |
| GND | — | GND | Common ground |

---

## Project Structure
gesture-car/
├── esp8266/
│   ├── car_firmware.ino       # ESP8266 WiFi + MQTT + motor control
│   └── pin_reference.md       # NodeMCU wiring reference
├── src/
│   ├── config.py              # All constants
│   ├── hand_utils.py          # MediaPipe + FastVoteBuffer
│   ├── collect_data.py        # Webcam data collection
│   ├── filter_images.py       # Image quality filter (one-time)
│   ├── extract_from_images.py # Images → landmark CSV
│   ├── train_model.py         # Train Random Forest
│   ├── export_model.py        # Export to ONNX for browser
│   └── app.py                 # Local Flask dev dashboard
├── docs/
│   ├── index.html             # Mobile control app (GitHub Pages)
│   ├── model.onnx             # Trained model for browser
│   ├── labels.json            # Gesture class labels
│   ├── sw.js                  # Service worker (offline cache)
│   └── manifest.json          # PWA manifest
├── templates/
│   └── index.html             # Local dev dashboard template
├── static/
│   ├── style.css              # Local dev dashboard styles
│   └── dashboard.js           # Local dev dashboard JS
├── outputs/
│   └── confusion_matrix.png   # Model evaluation result
├── requirements.txt
├── .gitignore
└── README.md

---

## Setup

### HiveMQ Cloud (one time)

Sign up at console.hivemq.cloud (free, no credit card)
Create Free Serverless Cluster
Access Management → create credentials:
username: gesturecar
password: GestureCar2024!
Note your cluster URL: xxxxxx.s1.eu.hivemq.cloud


### Update config (replace xxxxxx with your cluster URL)
esp8266/car_firmware.ino  → MQTT_BROKER
docs/index.html           → BROKER_URL
src/app.py                → MQTTSender.BROKER
src/config.py             → MQTT_BROKER

### Training pipeline
```bash
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt

python src/filter_images.py --dry-run   # preview
python src/filter_images.py             # execute
python src/extract_from_images.py       # images → CSV
python src/collect_data.py              # webcam samples
python src/train_model.py               # train + evaluate
python src/export_model.py              # → docs/model.onnx
```

### Deploy
```bash
git add docs/model.onnx docs/labels.json
git commit -m "Update model"
git push origin main
# GitHub Pages updates in ~2 minutes
```

### ESP8266

Set WIFI_SSID + WIFI_PASS in car_firmware.ino
Set MQTT_BROKER to your HiveMQ cluster URL
Arduino IDE → Tools → NodeMCU 1.0
Install library: PubSubClient by Nick O'Leary
Upload
Serial Monitor 115200 baud → should print: MQTT Connected ✓


### Laptop dev mode
```bash
python src/app.py
# Open http://localhost:5000
```

---

## ML Model

| Property | Value |
|---|---|
| Algorithm | Random Forest (100 trees) |
| Input | 63 features (21 landmarks × x,y,z normalized) |
| Classes | 5 gestures |
| Training samples | ~44,000 |
| CV accuracy | 97–99% |
| Inference | <1ms Python, ~5ms ONNX in browser |
| Format | ONNX opset 12 |

---

## Architecture
GitHub Pages (HTTPS)          HiveMQ Cloud (wss://)
docs/index.html        →      MQTT broker
model.onnx (cached)    →      topic: gesturecar/command
↓
ESP8266 (MQTT subscriber)
↓
L298N → 4 motors

---

## Confusion Matrix

![Confusion Matrix](outputs/confusion_matrix.png)

---

## License

MIT