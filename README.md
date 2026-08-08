# Gesture Car 🚗✋

### Browser-Based Hand Gesture Control for an IoT Car

Control a 4-wheel robotic car using hand gestures captured directly from a phone camera.

The project combines **MediaPipe hand tracking**, a lightweight **Random Forest classifier**, **ONNX Runtime Web**, **MQTT**, and an **ESP8266-based motor controller** into a browser-to-hardware control pipeline.

> **Open the web interface → show your hand → control the car.**

---

## 🎥 Demo

**Live controller:**
https://yash-patil-26.github.io/Gesture_car/

The controller is designed to run in a modern mobile browser. Gesture recognition happens locally in the browser, while MQTT is used to relay movement commands to the car.

### Supported gestures

|   Gesture  |   Command   | Description                      |
| :--------: | :---------: | -------------------------------- |
|   ✋ Palm   | **FORWARD** | Open hand facing the camera      |
|   ✊ Fist   |   **STOP**  | Fingers closed                   |
|   🤘 Rock  |   **LEFT**  | Index and pinky extended         |
|    👌 OK   |  **RIGHT**  | Thumb and index forming a circle |
| 👎 Dislike | **REVERSE** | Thumb pointing downward          |

A short frame-voting mechanism is used for movement gestures to reduce accidental commands during transitions. **STOP** is handled immediately.

---

## ✨ Key Features

* 📱 **Browser-based control**
  No dedicated mobile application is required for the controller.

* 🖐️ **Real-time hand gesture recognition**
  MediaPipe extracts 21 hand landmarks from the camera stream.

* 🧠 **Lightweight machine-learning model**
  A Random Forest classifies the landmark features into five gestures.

* 🌐 **ONNX browser inference**
  The trained model is exported to ONNX and executed using ONNX Runtime Web.

* 🔒 **Local gesture inference**
  Camera frames are processed in the browser. The application sends movement commands rather than camera frames to the MQTT layer.

* 📡 **MQTT communication**
  Commands are transmitted through HiveMQ between the browser and ESP8266.

* ⚡ **Hardware control**
  ESP8266 receives commands and controls four TT motors through an L298N driver.

* 🛑 **Command watchdog**
  The car stops if communication with the controller is lost for longer than the configured timeout.

* 💻 **Local development dashboard**
  A Flask-based development interface is included for testing the gesture pipeline and MQTT communication.

---

# 🏗️ System Architecture

```text
                         TRAINING PIPELINE
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  Gesture Data                                           │
│       │                                                 │
│       ▼                                                 │
│  Filtering → Landmark Extraction → Feature Preparation  │
│       │                                                 │
│       ▼                                                 │
│  Random Forest Training                                 │
│       │                                                 │
│       ▼                                                 │
│  ONNX Export                                             │
│       │                                                 │
└───────┼─────────────────────────────────────────────────┘
        │
        │ model.onnx + labels.json
        ▼
┌─────────────────────────────────────────────────────────┐
│                    MOBILE BROWSER                       │
│                                                         │
│  Phone Camera                                           │
│       │                                                 │
│       ▼                                                 │
│  MediaPipe Hand Tracking                                │
│       │                                                 │
│       ▼                                                 │
│  21 Hand Landmarks                                      │
│       │                                                 │
│       ▼                                                 │
│  ONNX Runtime Web                                       │
│       │                                                 │
│       ▼                                                 │
│  Gesture → Command                                      │
│       │                                                 │
│       ▼                                                 │
│  MQTT over Secure WebSocket                             │
└────────────────────────┬────────────────────────────────┘
                         │
                         │ MQTT
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    MQTT BROKER                          │
│                       HiveMQ                             │
└────────────────────────┬────────────────────────────────┘
                         │
                         │ MQTT / TCP
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  ESP8266 NODEMCU                        │
│                                                         │
│  Wi-Fi → MQTT Subscriber → Command Handler → Watchdog  │
│                                      │                  │
│                                      ▼                  │
│                              L298N Motor Driver         │
│                                      │                  │
│                                      ▼                  │
│                              4 × TT Motors              │
└─────────────────────────────────────────────────────────┘
```

### Why MQTT?

The browser controller runs in a secure HTTPS context, so communication with an external service needs to use a compatible secure transport. The browser connects to the MQTT broker using **WebSockets over TLS**, while the ESP8266 communicates with the broker using MQTT.

This keeps the communication layer independent from the physical motor-control hardware.

---

# 🧠 Machine Learning Pipeline

The project uses hand landmarks rather than raw camera images as the classifier input.

### Feature representation

MediaPipe provides:

* **21 hand landmarks**
* `x`, `y`, and `z` coordinates for each landmark
* **63 numerical features** in total

Before classification, the landmarks are normalized relative to the wrist and hand scale.

```text
Camera Frame
     │
     ▼
MediaPipe
     │
     ▼
21 Hand Landmarks
     │
     ▼
Normalization
     │
     ▼
63-Dimensional Feature Vector
     │
     ▼
Random Forest
     │
     ▼
Gesture Class + Confidence
     │
     ▼
Movement Command
```

### Model

| Property        | Value                           |
| --------------- | ------------------------------- |
| Algorithm       | Random Forest                   |
| Trees           | 100                             |
| Input           | 63 normalized landmark features |
| Classes         | 5                               |
| Output          | Gesture class + probabilities   |
| Training data   | ~25,000 samples                 |
| Export format   | ONNX                            |
| ONNX opset      | 12                              |
| Browser runtime | ONNX Runtime Web                |

The model is intentionally lightweight because the input is already a structured representation of the hand rather than raw image pixels.

---

# 🧪 Training Workflow

Training is performed offline. The resulting ONNX model is then deployed with the web application.

```text
Collect Gesture Samples
          ↓
Filter / Validate Data
          ↓
Extract Hand Landmarks
          ↓
Normalize Features
          ↓
Train Random Forest
          ↓
Evaluate Model
          ↓
Export to ONNX
          ↓
Deploy model.onnx
```

### Data collection

```bash
python src/collect_data.py
```

The collection utility uses a webcam to capture samples for the supported gesture classes.

### Training and export

```bash
python src/pipeline.py --stage train,export
```

The generated model can then be placed in:

```text
docs/model.onnx
```

along with:

```text
docs/labels.json
```

---

# 🔌 Hardware

| Component           | Role                                        |
| ------------------- | ------------------------------------------- |
| **ESP8266 NodeMCU** | Wi-Fi, MQTT communication and motor control |
| **L298N**           | Dual H-bridge motor driver                  |
| **4 × TT Motors**   | Differential-drive movement                 |
| **2 × 18650 cells** | Main power source                           |
| **Acrylic chassis** | Mechanical structure                        |
| **SPST switch**     | Main power control                          |

### Motor control

The ESP8266 translates high-level commands into motor directions.

```text
FORWARD  → Left + Right motors forward
REVERSE  → Left + Right motors reverse
LEFT     → Differential steering
RIGHT    → Differential steering
STOP     → All motors stopped
```

### Example GPIO mapping

| ESP8266     | L298N | Function              |
| ----------- | ----- | --------------------- |
| D1 / GPIO5  | IN1   | Left motor direction  |
| D2 / GPIO4  | IN2   | Left motor direction  |
| D5 / GPIO14 | IN3   | Right motor direction |
| D6 / GPIO12 | IN4   | Right motor direction |
| D7 / GPIO13 | ENA   | Left motor PWM        |
| D8 / GPIO15 | ENB   | Right motor PWM       |

> **Hardware note:** Motor-driver wiring and power connections should be verified against the specific L298N board and motor configuration being used. Do not power motors directly from the ESP8266.

---

# 🔄 Safety & Connection Handling

The controller includes basic communication safeguards.

### Command watchdog

The ESP8266 tracks the time since the last valid command.

```text
Command received
      │
      ▼
Reset watchdog
      │
      ▼
Drive motors
      │
      └──── No command within timeout
                    │
                    ▼
                  STOP
```

This prevents the car from continuing to drive when the controller loses communication.

### Controller states

| State             | Meaning                                        |
| ----------------- | ---------------------------------------------- |
| 🟡 Connecting     | Attempting to connect to the MQTT broker       |
| 🟡 Device offline | Broker is reachable but the car is unavailable |
| 🟢 Connected      | Controller and car are communicating           |
| 🔴 Busy           | Another controller is already using the device |

---

# 🚀 Getting Started

## Requirements

### Software

* Python 3.x
* Git
* Arduino IDE
* ESP8266 board support
* A modern browser with camera access

### Python dependencies

Install the project dependencies with:

```bash
pip install -r requirements.txt
```

### Hardware

* ESP8266 NodeMCU
* L298N motor driver
* 4 × TT gear motors
* Chassis
* Battery pack
* Jumper wires
* Appropriate power switch

---

## 1. Clone the repository

```bash
git clone https://github.com/yash-patil-26/Gesture_Car.git
cd Gesture_Car
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 2. Configure MQTT

Create your local MQTT configuration using the project's configuration files.

Do **not** commit real broker credentials, Wi-Fi passwords, or other secrets to Git.

Example configuration:

```python
MQTT_BROKER = "your-broker-host"
MQTT_USERNAME = "your-username"
MQTT_PASSWORD = "your-password"
```

The ESP8266 firmware requires corresponding Wi-Fi and MQTT configuration.

---

## 3. Collect training data

```bash
python src/collect_data.py
```

Follow the prompts to record examples for each gesture.

For better generalization, training data should contain variation in:

* Hand position
* Distance from camera
* Rotation
* Lighting
* Background
* Different users

---

## 4. Train and export the model

```bash
python src/pipeline.py --stage train,export
```

The exported model should be available to the browser application as:

```text
docs/model.onnx
docs/labels.json
```

---

## 5. Flash the ESP8266

Open:

```text
esp8266/car_firmware/car_firmware.ino
```

In Arduino IDE:

```text
Board → NodeMCU 1.0 (ESP-12E Module)
```

Install:

```text
PubSubClient
```

Configure Wi-Fi and MQTT credentials, then upload the firmware.

Open the serial monitor at:

```text
115200 baud
```

A successful MQTT connection should be reported by the firmware.

---

# 🌐 Run the Web Controller

The production controller is available through GitHub Pages:

**https://yash-patil-26.github.io/Gesture_car/**

On a compatible phone:

1. Open the controller.
2. Allow camera access.
3. Start the controller.
4. Show a supported gesture.
5. The corresponding command is sent to the car.

The browser handles gesture recognition locally. The MQTT layer receives the resulting movement command.

---

# 💻 Development Mode

For local development:

```bash
python src/app.py
```

Then open:

```text
http://localhost:5000
```

The development interface provides tools for testing the gesture-recognition pipeline, MQTT connectivity, and command flow without relying on the deployed GitHub Pages interface.

---

# 📁 Project Structure

```text
Gesture_Car/
│
├── docs/
│   ├── index.html              # Browser controller
│   ├── model.onnx              # ONNX gesture model
│   └── labels.json             # Gesture labels and commands
│
├── esp8266/
│   └── car_firmware/
│       └── car_firmware.ino    # ESP8266 firmware
│
├── src/
│   ├── app.py                  # Local development server
│   ├── collect_data.py         # Gesture data collection
│   ├── config.py               # Configuration and ML utilities
│   └── pipeline.py             # Training and ONNX export
│
├── outputs/
│   └── confusion_matrix.png    # Model evaluation output
│
├── requirements.txt
└── README.md
```

---

# 🧩 Technology Stack

### Frontend / Browser

* HTML
* CSS
* JavaScript
* MediaPipe
* ONNX Runtime Web
* WebSocket MQTT

### Machine Learning

* Python
* scikit-learn
* Random Forest
* ONNX

### IoT

* ESP8266
* Arduino
* MQTT
* HiveMQ
* L298N
* TT DC motors

### Development

* Flask
* Git
* GitHub Pages
* Arduino IDE

---

# 📊 Project Highlights

This project demonstrates an end-to-end system rather than an isolated ML model:

```text
Machine Learning
       +
Computer Vision
       +
Web Development
       +
MQTT / Networking
       +
Embedded Systems
       +
Motor Control
```

The interesting engineering challenge is the boundary between these layers: a gesture recognized by a browser becomes a network message, which becomes a hardware command and ultimately physical movement.

---

# ⚠️ Current Scope & Limitations

This is a prototype-oriented robotics project.

Current limitations include:

* Gesture recognition depends on camera quality and lighting.
* The trained model is limited to the gesture classes represented in the dataset.
* MQTT connectivity is required for remote browser-to-car communication.
* Motor performance depends on battery condition, chassis weight, motor variation, and surface.
* The L298N introduces voltage loss compared with more modern motor-driver designs.
* Browser camera permissions and secure-context requirements apply to the deployed controller.

These constraints are part of the current implementation and provide clear areas for future improvement.

---

# 🔮 Possible Improvements

Potential future development includes:

* Additional gesture classes
* Better dataset collection and evaluation
* Model benchmarking against alternative classifiers
* Improved motor-driver hardware
* Variable-speed gesture control
* Obstacle detection
* Autonomous/manual hybrid driving
* Multi-car addressing through MQTT
* Mobile UI improvements
* More detailed telemetry and diagnostics

---

# 📌 Why This Project?

Gesture Car explores a practical combination of **edge machine learning, browser-based computer vision, IoT messaging, and embedded robotics**.

Instead of sending camera frames to a server, the system reduces the vision problem to a compact landmark representation and performs classification on the client device. The resulting command is then transmitted through MQTT to a resource-constrained microcontroller.

That architecture makes the project a useful study of how modern web technologies and lightweight ML can interact with physical hardware.

---

# 📜 License

This project is released under the **MIT License**.

See [`LICENSE`](LICENSE) for details.

---

## 👤 Author

**Yash Patil**

GitHub:
https://github.com/yash-patil-26

---

<p align="center">
  Built with MediaPipe · ONNX · MQTT · ESP8266 · Python · JavaScript
</p>
