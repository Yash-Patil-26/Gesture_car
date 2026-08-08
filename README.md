# 🤖 Gesture Car

### Browser-based hand gesture control for a 4-wheel robotic car.

**📱 Phone camera → MediaPipe → ONNX Random Forest → MQTT → ESP8266 → 🚗 Motors**

[🌐 Live Demo](https://github.com/Yash-Patil-26/Gesture_car/issues/1#issue-5099027166)

Open the demo on a phone, allow camera access, and control the car using hand gestures. Gesture inference runs locally in the browser, so camera frames are not sent to the application server.

---

## 🎮 Gestures

|     Gesture    |   Command   |
| :------------: | :---------: |
|     ✋ Palm     | **FORWARD** |
|     ✊ Fist     |   **STOP**  |
|     🤘 Rock    |   **LEFT**  |
|      👌 OK     |  **RIGHT**  |
| 👎 Thumbs Down | **REVERSE** |

Movement commands require **2 consecutive matching frames** before triggering. **STOP** is handled immediately.

---

## 🏗️ Architecture

```text
┌──────────────────────────────────────────────────────┐
│                    MOBILE BROWSER                    │
│                                                      │
│  📷 Camera → MediaPipe → 21 Landmarks → ONNX Model │
│                                      │               │
│                                      ▼               │
│                              Gesture → Command       │
└──────────────────────────────┬───────────────────────┘
                               │
                         MQTT over WSS
                               │
                               ▼
                       ┌───────────────┐
                       │    HiveMQ     │
                       └───────┬───────┘
                               │ MQTT
                               ▼
┌──────────────────────────────────────────────────────┐
│                      ESP8266                         │
│                MQTT → Watchdog → L298N               │
│                              │                       │
│                       4 × TT Motors 🚗               │
└──────────────────────────────────────────────────────┘
```

### Why this design?

**Local ML:** MediaPipe extracts hand landmarks in the browser, and ONNX Runtime Web performs classification locally.

**MQTT:** Secure WebSocket MQTT connects the HTTPS browser to the broker, while the ESP8266 uses MQTT directly.

**Watchdog:** If commands stop arriving for the configured timeout, the ESP8266 stops the motors.

---

## 🧠 ML Model

The model classifies **21 hand landmarks × (x, y, z) = 63 features** rather than raw camera frames.

```text
Camera
  ↓
MediaPipe
  ↓
21 Hand Landmarks
  ↓
Wrist + Scale Normalization
  ↓
63 Features
  ↓
Random Forest
  ↓
ONNX
  ↓
Browser Inference
```

| Property         | Value                  |
| ---------------- | ---------------------- |
| Algorithm        | Random Forest          |
| Trees            | 100                    |
| Input            | 63 normalized features |
| Classes          | 5                      |
| Training samples | ~25,000                |
| Cross-validation | ~97–99%                |
| Export           | ONNX opset 12          |
| Browser runtime  | ONNX Runtime Web       |

`zipmap=False` is used during export so class probabilities are available directly as a tensor.

> Accuracy is based on the collected dataset and cross-validation procedure; real-world performance can vary across users, cameras and lighting.

---

## 🚗 Hardware

| Component       | Role                        |
| --------------- | --------------------------- |
| ESP8266 NodeMCU | Wi-Fi, MQTT & motor control |
| L298N           | H-bridge motor driver       |
| 4 × TT Motors   | Differential drive          |
| 2 × 18650       | Battery                     |
| Acrylic chassis | Robot platform              |
| SPST switch     | Main power                  |

### Motor control

```text
ESP8266
   │
   ▼
L298N
 ┌─┴─┐
 ▼   ▼
Left Right
Motors Motors
```

> ⚠️ Remove the L298N ENA/ENB jumpers when using PWM control through D7/D8.

---

## 📁 Project Structure

```text
Gesture_Car/
│
├── docs/
│   ├── index.html          # Web controller
│   ├── model.onnx          # ML model
│   └── labels.json         # Gesture mapping
│
├── esp8266/
│   └── car_firmware/
│       └── car_firmware.ino
│
├── src/
│   ├── config.py
│   ├── pipeline.py         # Train + export
│   ├── collect_data.py     # Data collection
│   └── app.py              # Local Flask dashboard
│
├── outputs/
│   └── confusion_matrix.png
│
├── requirements.txt
└── README.md
```

---

# ⚡ Quick Start

### 1. Clone

```bash
git clone https://github.com/yash-patil-26/Gesture_Car.git
cd Gesture_Car

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure MQTT

Set credentials in `src/config.py` and `esp8266/car_firmware/car_firmware.ino`.

```python
MQTT_BROKER   = "your-broker-host"
MQTT_USERNAME = "your-username"
MQTT_PASSWORD = "your-password"
```

**Do not commit real credentials.**

### 3. Train

```bash
python src/collect_data.py
python src/pipeline.py --stage train,export
```

Generated browser assets:

```text
docs/model.onnx
docs/labels.json
```

### 4. Flash ESP8266

Open:

```text
esp8266/car_firmware/car_firmware.ino
```

Arduino IDE:

```text
Board → NodeMCU 1.0 (ESP-12E Module)
Library → PubSubClient
```

Configure Wi-Fi + MQTT credentials and upload.

### 5. Run

Open:

[https://yash-patil-26.github.io/Gesture_car/]

Then:

**Power car → Start controller → Allow camera → Show gesture**

---

## 🖥️ Development Mode

```bash
python src/app.py
```

Open:

```text
http://localhost:5000
```

The local dashboard provides camera, gesture, MQTT and command visibility during development.

---

## 📡 Connection States

| Status                      | Meaning                       |
| --------------------------- | ----------------------------- |
| 🟡 Connecting               | Connecting to MQTT broker     |
| 🟡 Device not connected     | Broker available, car offline |
| 🟢 Connected                | Car online and ready          |
| 🔴 Device already connected | Another controller is active  |

---

## 🛠️ Tech Stack

**Computer Vision:** MediaPipe
**ML:** Python · scikit-learn · Random Forest · ONNX
**Browser:** HTML · CSS · JavaScript · ONNX Runtime Web
**IoT:** MQTT · HiveMQ
**Embedded:** ESP8266 · Arduino · PubSubClient · L298N
**Deployment:** GitHub Pages
**Development:** Flask

---

## 🔬 Engineering Highlights

* Custom hand-gesture dataset and training pipeline
* Random Forest → ONNX browser deployment
* Client-side ML inference
* MQTT browser-to-ESP8266 communication
* Embedded motor-control firmware
* Gesture confirmation logic
* Communication watchdog / fail-safe stop
* Static web deployment through GitHub Pages

---

## 🔮 Future Scope

* More gesture classes
* Improved cross-user robustness
* Battery telemetry
* Obstacle detection
* Local/offline communication
* Autonomous navigation
* Hardware status monitoring

---

## 📜 License

MIT License

---

<div align="center">

### Computer Vision × Machine Learning × IoT × Robotics

**Built by Yash Patil**

https://github.com/Yash-Patil-26

⭐ Star the repository if you find it interesting.

</div>
