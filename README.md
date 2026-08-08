<div align="center">

<h1>
  <img src="https://readme-typing-svg.demolab.com?font=Segoe+UI&weight=700&size=32&pause=1000&color=00E5A0&center=true&vCenter=true&width=500&lines=Gesture+RC+Car" alt="Gesture RC Car"/>
</h1>

<p><strong>Control a real RC car with hand gestures — through any phone browser, from anywhere in the world.</strong></p>

<p>
  <a href="https://yash-patil-26.github.io/Gesture_car/">
    <img src="https://img.shields.io/badge/▶ Try Live Demo-00E5A0?style=for-the-badge&logoColor=black" alt="Live Demo"/>
  </a>
  &nbsp;
  <img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  &nbsp;
  <img src="https://img.shields.io/badge/ESP8266-NodeMCU-E7352C?style=for-the-badge&logo=arduino&logoColor=white" alt="ESP8266"/>
  &nbsp;
  <img src="https://img.shields.io/badge/License-MIT-gray?style=for-the-badge" alt="MIT"/>
</p>

</div>

---

<!--
  ═══════════════════════════════════════════════════
  HOW TO ADD YOUR DEMO VIDEO (one time, takes 2 min)
  ═══════════════════════════════════════════════════
  1. Go to github.com/yash-patil-26/Gesture_Car/issues
  2. Click "New Issue"
  3. Drag your demo.mp4 into the comment box
  4. Wait for upload — GitHub gives you a URL like:
     https://github.com/yash-patil-26/Gesture_Car/assets/XXXXXXX/XXXXXX.mp4
  5. Copy that URL and replace the placeholder below
  6. Delete this comment block
  ═══════════════════════════════════════════════════
-->

https://github.com/user-attachments/assets/304a75fb-850f-4141-9bdb-6fb4176caa54

> *Open the URL on any phone → show your hand → car moves*

---

## How it works

Phone camera → MediaPipe.js → ONNX Random Forest → HiveMQ MQTT
(any browser) 21 hand landmarks gesture class <5ms wss:// cloud relay

HiveMQ → ESP8266 NodeMCU → L298N driver → 4× TT motors → 🚗


All ML runs locally in the phone browser. No frames leave your device.
Close the browser tab — car stops automatically.

---

## Gestures

<div align="center">

| Gesture | Hand shape | Command |
|:---:|:---:|:---:|
| ✋ Palm | Open hand facing camera | **FORWARD** |
| ✊ Fist | All fingers closed | **STOP** |
| 🤘 Rock | Index + pinky extended | **LEFT** |
| 👌 OK | Thumb + index circle | **RIGHT** |
| 👎 Dislike | Thumbs down | **REVERSE** |

</div>

> A 2-frame vote buffer requires 2 consecutive matching frames before triggering motion — eliminating false triggers from gesture transitions. STOP fires in a single frame.

---

## Architecture

┌─────────────────────────────────────────────────────────┐
│ TRAINING (laptop, one-time) │
│ │
│ input_data/ → filter → extract landmarks → collect │
│ → train Random Forest → export ONNX → push to Pages │
└────────────────────────┬────────────────────────────────┘
│ model.onnx + labels.json
▼
┌─────────────────────────────────────────────────────────┐
│ MOBILE BROWSER (demo — any phone, any network) │
│ │
│ GitHub Pages serves index.html │
│ MediaPipe.js detects 21 hand landmarks │
│ ONNX Runtime Web classifies gesture <5ms │
│ Publishes command string via HiveMQ wss://:8884 │
└────────────────────────┬────────────────────────────────┘
│ ~80ms cloud relay
▼
┌─────────────────────────────────────────────────────────┐
│ ESP8266 NodeMCU (on the car) │
│ │
│ Subscribes to HiveMQ TCP:8883 │
│ Drives L298N → 4 TT motors │
│ Watchdog: stops if silent > 2000ms │
└─────────────────────────────────────────────────────────┘


### Why this design

**Cloud MQTT over direct WebSocket** — browsers served on HTTPS block unencrypted `ws://` connections. ESP8266 cannot run TLS. A cloud broker with `wss://` on the browser side and plain TCP on the car side solves this permanently without any hardware change.

**Random Forest over CNN** — the 21 landmark coordinates are already a high-level representation. A tree classifier generalises well at this scale, gives calibrated probabilities for confidence gating, and runs in under 1ms. No GPU, no overfit risk at 25k samples.

**ONNX over direct sklearn** — sklearn cannot run in a browser. ONNX with `zipmap=False` exports probabilities as a plain float32 tensor that onnxruntime-web reads directly.

---

## ML model

<div align="center">

| Property | Value |
|:---|:---|
| Algorithm | Random Forest — 100 trees |
| Input | 63 floats · 21 landmarks × (x,y,z) · wrist-normalised · scale-normalised |
| Classes | 5 — dislike · fist · ok · palm · rock |
| Training samples | ~25,000 balanced |
| Cross-validation accuracy | 97–99% |
| Inference | <1ms Python · ~5ms ONNX WASM in browser |
| Export format | ONNX opset 12 · `zipmap=False` → `probabilities` tensor |

</div>

<details>
<summary><b>Confusion matrix</b></summary>
<br/>
<div align="center">
<img src="outputs/confusion_matrix.png" width="500" alt="Confusion matrix"/>
</div>
</details>

---

## Hardware

<div align="center">

| Component | Spec | Role |
|:---|:---|:---|
| ESP8266 NodeMCU | AI-Thinker · 80MHz · 80KB RAM | WiFi + MQTT subscriber + motor logic |
| L298N motor driver | H-bridge · 2A/channel | Drives left and right motor pairs |
| TT motors × 4 | 3–6V · 200RPM | Differential drive |
| 18650 × 2 (series) | 7.4V · ~2200mAh | Power supply |
| Acrylic chassis | 200×160mm | Structure |
| SPST switch | — | Master power kill |

</div>

### Wiring

Battery(+) → SPST switch → L298N 12V terminal
Battery(−) ─────────────→ L298N GND → ESP8266 GND
L298N 5V out → ESP8266 VIN

ESP8266 → L298N:
D1 (GPIO5) → IN1 D2 (GPIO4) → IN2 ← left motors
D5 (GPIO14) → IN3 D6 (GPIO12) → IN4 ← right motors
D7 (GPIO13) → ENA D8 (GPIO15) → ENB ← PWM speed


> ⚠️ Remove the yellow ENA/ENB jumpers from L298N before connecting D7/D8

---

## Quick start

### 1 · Clone and install

```bash
git clone https://github.com/yash-patil-26/Gesture_Car.git
cd Gesture_Car
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
```

### 2 · Configure

Set your credentials in **two files**:

`src/config.py`
```python
MQTT_BROKER   = "your-cluster.s1.eu.hivemq.cloud"
MQTT_USERNAME = "your-username"
MQTT_PASSWORD = "your-password"
```

`esp8266/car_firmware/car_firmware.ino`
```cpp
const char* WIFI_SSID   = "YourWiFiName";
const char* WIFI_PASS   = "YourWiFiPassword";
const char* MQTT_BROKER = "your-cluster.s1.eu.hivemq.cloud";
const char* MQTT_USER   = "your-username";
const char* MQTT_PASS   = "your-password";
```

### 3 · Collect samples and train

```bash
# Collect live webcam samples
python src/collect_data.py
# Enter number of people → each records 5 samples per gesture

# Train and export to browser format
python src/pipeline.py --stage train,export
```

### 4 · Deploy

```bash
git add docs/model.onnx docs/labels.json
git commit -m "update model"
git push
# GitHub Pages rebuilds in ~2 minutes
```

### 5 · Flash ESP8266

Arduino IDE:
Board → NodeMCU 1.0 (ESP-12E Module)
Library → PubSubClient by Nick O'Leary (Library Manager)
Upload → esp8266/car_firmware/car_firmware.ino
Monitor → 115200 baud → expect: [MQTT] Connected


### 6 · Run demo

Power on car → open https://yash-patil-26.github.io/Gesture_car/ → tap Start


---

## Development mode (laptop)

```bash
python src/app.py
# http://localhost:5000
# Live camera feed · gesture detection · MQTT status · command log
```

---

## Project structure

Gesture_Car/
│
├── docs/ # GitHub Pages — mobile control app
│ ├── index.html # Complete gesture UI — runs in browser
│ ├── model.onnx # Trained model for ONNX WASM inference
│ └── labels.json # Gesture names + command mapping
│
├── esp8266/car_firmware/
│ └── car_firmware.ino # WiFi + MQTT + L298N motor control
│
├── src/
│ ├── config.py # All constants + shared ML utilities
│ ├── pipeline.py # filter → extract → train → export
│ ├── collect_data.py # Live webcam gesture data collection
│ └── app.py # Laptop dev dashboard (Flask)
│
├── outputs/
│ └── confusion_matrix.png
│
└── requirements.txt


---

## Connection states

| Status | Meaning |
|:---|:---|
| 🟡 Connecting to broker… | Reaching HiveMQ |
| 🟡 Device not connected | Broker OK — car not powered or not on WiFi |
| 🟢 Connected successfully | Car online and ready |
| 🔴 Try later! Device already connected | Another user is controlling the car |

---

## Tech stack

<div align="center">

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=flat-square&logo=opencv&logoColor=white)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0097A7?style=flat-square&logo=google&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=flat-square&logo=scikit-learn&logoColor=white)
![ONNX](https://img.shields.io/badge/ONNX-005CED?style=flat-square&logo=onnx&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=flat-square&logo=flask&logoColor=white)
![MQTT](https://img.shields.io/badge/MQTT-HiveMQ-FF6B35?style=flat-square)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat-square&logo=javascript&logoColor=black)
![Arduino](https://img.shields.io/badge/Arduino-00979D?style=flat-square&logo=arduino&logoColor=white)
![ESP8266](https://img.shields.io/badge/ESP8266-E7352C?style=flat-square&logo=espressif&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/GitHub_Pages-222222?style=flat-square&logo=github&logoColor=white)

</div>

---

## License

MIT — free to use, modify, and build on.

---

<div align="center">
<sub>
Built as an end-to-end ML + embedded systems prototype ·
<a href="https://yash-patil-26.github.io/Gesture_car/">Try it live</a>
</sub>
</div>