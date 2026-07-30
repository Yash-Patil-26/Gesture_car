<div align="center">

# Gesture RC Car

**Control a physical RC car with hand gestures — through your phone camera, entirely in the browser.**

<br/>

[![Live Demo](https://img.shields.io/badge/Try%20It%20Live-00E5A0?style=for-the-badge&logoColor=black)](https://yash-patil-26.github.io/Gesture_Car/)
[![License: MIT](https://img.shields.io/badge/License-MIT-gray?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python_3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Arduino](https://img.shields.io/badge/ESP8266-00979D?style=for-the-badge&logo=arduino&logoColor=white)](esp8266/)

<br/>


![Demo](docs/assets/demo.gif)

*Open the URL. Show your hand. The car moves.*

</div>

---

## Overview

Most gesture-controlled projects need a glove, a special sensor, or a laptop sitting next to the hardware. This one needs none of those. It runs entirely in a phone browser — no app install, no wearable, no dedicated server.

You open a URL. The browser loads a trained ML model. Your front camera feeds hand landmarks into a Random Forest classifier. Commands travel through a cloud MQTT broker to an ESP8266 on the car. Close the tab and the car stops.

---

## Architecture

Phone camera → MediaPipe (21 landmarks)
→ Random Forest ONNX (gesture class, <5ms)
→ HiveMQ wss:// (cloud MQTT relay, ~80ms)
→ ESP8266 NodeMCU
→ L298N → 4× TT motors


The ML model runs locally on the phone — no camera frames ever leave the device. Only the classified command string (`FORWARD`, `LEFT`, etc.) is sent over the network.


---

## Tech Stack

| Category | Technology |
|---|---|
| Computer Vision | MediaPipe Hands |
| Machine Learning | Random Forest, scikit-learn, ONNX |
| Frontend | HTML, CSS, JavaScript |
| Backend | Flask |
| Communication | MQTT (HiveMQ Cloud) |
| Hardware | ESP8266 NodeMCU, L298N, TT Motors |
| Deployment | GitHub Pages |

---

## Gestures

| Gesture | Command |
|---|---|
| ✋ Open palm | Forward |
| ✊ Closed fist | Stop |
| ☝️ Index left | Left |
| ☝️ Index right | Right |
| 👎 Thumbs down | Reverse |

A vote buffer requires 3 consecutive matching frames before triggering a motion command — eliminating noise from gesture transitions. Stop fires in a single frame.

---

## Hardware

| Part | Detail |
|---|---|
| ESP8266 NodeMCU | WiFi + MQTT subscriber + motor logic |
| L298N motor driver | H-bridge, 2A/channel |
| 4× TT motors | 3–6V, left/right pairs in parallel |
| 2× 18650 (series) | 7.4V supply → L298N |
| Acrylic chassis | 200×160mm base |

**Wiring in short:** batteries → L298N → 5V out → NodeMCU VIN. Control signals: D1/D2 → IN1/IN2 (left), D5/D6 → IN3/IN4 (right), D7 → ENA, D8 → ENB. Remove ENA/ENB jumpers before wiring D7/D8.

---

## Machine Learning

| | |
|---|---|
| Model | Random Forest, 100 trees |
| Input | 63 floats — 21 landmarks × (x,y,z), wrist-normalised |
| Training data | ~44k samples (filtered Kaggle images + webcam) |
| CV accuracy | 97–99% |
| Export | ONNX opset 12 via skl2onnx, runs in browser via WASM |

A CNN would be excessive here. The landmark vector is already a high-level representation — a tree-based model generalises well at this scale, gives calibrated probabilities, and runs in <1ms.

<details>
<summary>Confusion matrix</summary>
<br/>
<img src="outputs/confusion_matrix.png" width="480"/>
</details>

---

## Quick Start

**Prerequisites:** Python 3.9+, Arduino IDE, free [HiveMQ Cloud](https://console.hivemq.cloud) account (no credit card).

**1. Clone and install**
```bash
git clone https://github.com/yash-patil-26/Gesture_Car.git
cd Gesture_Car
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
```

**2. Configure** — replace `xxxxxxxxxxxxxxxx` with your HiveMQ cluster URL in:
- `src/config.py` → `MQTT_BROKER`
- `esp8266/car_firmware.ino` → `MQTT_BROKER`, `WIFI_SSID`, `WIFI_PASS`

**3. Run the ML pipeline**
```bash
python src/pipeline.py                         # full run: filter → extract → train → export
python src/pipeline.py --stage train,export    # skip image processing if data exists
```

**4. Flash the ESP8266**

Library Manager → install PubSubClient (Nick O'Leary)
Board: NodeMCU 1.0 (ESP-12E Module)
Upload esp8266/car_firmware.ino
Serial Monitor @ 115200 → expect: [MQTT] ✓ Connected


**5. Deploy**
```bash
git add docs/model.onnx docs/labels.json
git commit -m "update model" && git push
# GitHub Pages rebuilds in ~2 minutes
```

**6. Run**

Power on car → open https://yash-patil-26.github.io/Gesture_Car/ on any phone


---

## Local Development

```bash
python src/app.py
# http://localhost:5000 — live camera feed, command log, MQTT status
```

---

## Project structure

├── docs/               # GitHub Pages — mobile control app
│   ├── index.html
│   ├── model.onnx
│   └── labels.json
├── esp8266/
│   └── car_firmware.ino
├── src/
│   ├── config.py       # constants + shared utilities
│   ├── hand_utils.py   # MediaPipe helpers + FastVoteBuffer
│   ├── collect_data.py # webcam data collection
│   ├── filter_images.py
│   ├── extract_from_images.py
│   ├── train_model.py
│   ├── export_model.py
│   └── app.py          # local dev dashboard
└── outputs/
    └── confusion_matrix.png


---

## Engineering Decisions

**The HTTPS/WebSocket problem.** GitHub Pages forces HTTPS. Browsers block `ws://` from HTTPS pages. The ESP8266 can't run TLS. Solution: route commands through a cloud MQTT broker — the browser uses `wss://` to the broker, the ESP8266 connects outward as a plain TCP client. No local network required at all.

**Model size vs browser.** Random Forest ONNX exports can hit 20MB+. Keeping training data balanced and capping trees at 100 held it under 15MB — acceptable for a first load that caches permanently.

---



---

## Performance

| Metric | Value |
|---|---:|
| Gesture Classes | 5 |
| Cross-validation Accuracy | 97–99% |
| Browser Inference | <5 ms |
| MQTT Latency | ~80 ms |
| Model | Random Forest (100 Trees) |

## Future Improvements

- [ ] Replace Random Forest with a quantised TFLite model for smaller binary
- [ ] Dynamic gestures (swipe sequences) via LSTM
- [ ] Battery level telemetry over MQTT status topic
- [ ] OTA firmware update over MQTT

---

## License

MIT — do whatever you want with it.

---

<div align="center">
<sub>Built as an end-to-end ML + embedded systems prototype · <a href="https://yash-patil-26.github.io/Gesture_Car/">Try it live</a></sub>
</div>