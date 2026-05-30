# src/app.py
# ─────────────────────────────────────────────────────────────
# Mode A — Laptop gesture control dashboard.
# Laptop webcam → MediaPipe → ML → MQTT → HiveMQ → ESP8266
#
# Run: python src/app.py
# Open: http://localhost:5000
# ─────────────────────────────────────────────────────────────

import os
import sys
import cv2
import pickle
import time
import threading
import numpy as np
from collections import deque

import mediapipe as mp
import paho.mqtt.client as mqtt_client
from flask import Flask, Response, render_template, jsonify
from flask_socketio import SocketIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    MODEL_FILE, ENCODER_FILE,
    CAM_INDEX, CAM_WIDTH, CAM_HEIGHT,
    MP_DETECTION_CONFIDENCE, MP_TRACKING_CONFIDENCE,
    CONFIDENCE_THRESHOLD, VOTE_WINDOW,
    FLASK_HOST, FLASK_PORT
)
from hand_utils import (
    build_hand_detector, process_frame,
    get_landmark_list, extract_features,
    FastVoteBuffer
)

# ── MQTT config ────────────────────────────────────────────────
# Must match esp8266/car_firmware.ino
MQTT_BROKER   = "xxxxxxxx.s1.eu.hivemq.cloud"  # update this
MQTT_PORT     = 8883
MQTT_USER     = "gesturecar"
MQTT_PASSWORD = "YourHiveMQPassword"            # update this
MQTT_TOPIC    = "gesture/car/command"
MQTT_STATUS   = "gesture/car/status"
CONTROLLER_ID = "laptop_mode_a"

# ── Flask setup ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)
app.config['SECRET_KEY'] = 'gesture_car_mode_a'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ── Shared state ───────────────────────────────────────────────
frame_lock = threading.Lock()
state = {
    "frame":       None,
    "gesture":     "—",
    "confidence":  0.0,
    "command":     "STOP",
    "car_ready":   False,
    "fps":         0.0,
    "stats":       {"forward":0,"reverse":0,"left":0,"right":0,"stop":0},
}


def load_model():
    if not os.path.exists(MODEL_FILE):
        raise FileNotFoundError(
            f"Model not found: {MODEL_FILE}\n"
            "Run: python src/train_model.py"
        )
    with open(MODEL_FILE,   'rb') as f: model   = pickle.load(f)
    with open(ENCODER_FILE, 'rb') as f: encoder = pickle.load(f)
    print(f"[ML] Model loaded — classes: {list(encoder.classes_)}")
    return model, encoder


# ── MQTT publisher ─────────────────────────────────────────────

class MQTTPublisher:
    def __init__(self):
        self.client    = mqtt_client.Client(
            client_id  = CONTROLLER_ID,
            clean_session = True
        )
        self.client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        self.client.tls_set()  # TLS for HiveMQ
        self.connected = False
        self.last_cmd  = None
        self.last_sent = 0
        self._setup_callbacks()

    def _setup_callbacks(self):
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                self.connected = True
                client.subscribe(MQTT_STATUS)
                client.publish(MQTT_TOPIC,
                    f"{CONTROLLER_ID}:CONNECT", qos=0)
                print("[MQTT] Connected to broker")
            else:
                print(f"[MQTT] Connection failed: rc={rc}")

        def on_disconnect(client, userdata, rc):
            self.connected = False
            print("[MQTT] Disconnected")

        def on_message(client, userdata, msg):
            m = msg.payload.decode()
            if f"READY:{CONTROLLER_ID}" in m:
                state["car_ready"] = True
                print("[MQTT] Car ready for Mode A")
            elif "BUSY" in m:
                state["car_ready"] = False
                print("[MQTT] Car busy — another controller active")

        self.client.on_connect    = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_message    = on_message

    def connect(self):
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
            self.client.loop_start()
        except Exception as e:
            print(f"[MQTT] Connect error: {e}")

    def send(self, command: str):
        if not self.connected or not state["car_ready"]:
            return
        now     = time.time()
        changed = command != self.last_cmd
        beat    = now - self.last_sent > 0.4

        if changed or beat:
            payload = f"{CONTROLLER_ID}:{command}"
            self.client.publish(MQTT_TOPIC, payload, qos=0)
            self.last_cmd  = command
            self.last_sent = now

    def disconnect(self):
        if self.connected:
            self.client.publish(MQTT_TOPIC,
                f"{CONTROLLER_ID}:DISCONNECT", qos=0)
            self.client.publish(MQTT_TOPIC,
                f"{CONTROLLER_ID}:STOP", qos=0)
        self.client.loop_stop()
        self.client.disconnect()


# ── Inference thread ───────────────────────────────────────────

def inference_thread(model, encoder, publisher):
    detector = build_hand_detector(
        MP_DETECTION_CONFIDENCE,
        MP_TRACKING_CONFIDENCE
    )
    vote_buf = FastVoteBuffer(CONFIDENCE_THRESHOLD)

    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          30)

    if not cap.isOpened():
        print(f"[CAM] Cannot open camera {CAM_INDEX}")
        return

    print(f"[CAM] Camera opened")

    mp_draw     = mp.solutions.drawing_utils
    mp_hands_m  = mp.solutions.hands
    fps         = 0.0
    t_prev      = time.time()
    emit_cnt    = 0
    gesture     = "—"
    confidence  = 0.0
    command     = "STOP"

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        frame     = cv2.flip(frame, 1)
        result, _ = process_frame(frame, detector)
        lms       = get_landmark_list(result)

        if lms is not None:
            mp_draw.draw_landmarks(
                frame,
                result.multi_hand_landmarks[0],
                mp_hands_m.HAND_CONNECTIONS,
                mp_draw.DrawingSpec(
                    color=(0,180,255), thickness=2, circle_radius=3),
                mp_draw.DrawingSpec(
                    color=(255,255,255), thickness=1)
            )
            features   = extract_features(lms).reshape(1, -1)
            proba      = model.predict_proba(features)[0]
            idx        = int(np.argmax(proba))
            confidence = float(proba[idx])
            gesture    = encoder.classes_[idx]
            command    = vote_buf.update(gesture, confidence, True)
        else:
            command    = vote_buf.update("stop", 0.0, False)
            gesture    = "No hand"
            confidence = 0.0

        publisher.send(command)

        # Annotate frame
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0,0), (w,82), (18,18,18), -1)
        color = (0,220,100) if confidence >= CONFIDENCE_THRESHOLD \
                else (80,80,220)
        cv2.putText(frame, f"Gesture: {gesture}",
                    (16,38), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2)
        bar_w = int(confidence * 200)
        cv2.rectangle(frame, (16,52), (216,66), (50,50,50), -1)
        cv2.rectangle(frame, (16,52), (16+bar_w,66), color, -1)
        cv2.putText(frame, command,
                    (w-180,56), cv2.FONT_HERSHEY_SIMPLEX, 1.1,
                    (0,220,100), 2)

        # FPS
        t_now  = time.time()
        fps    = 0.9*fps + 0.1*(1.0/max(t_now-t_prev,1e-6))
        t_prev = t_now

        with frame_lock:
            state["frame"]      = frame.copy()
            state["gesture"]    = gesture
            state["confidence"] = round(confidence, 3)
            state["command"]    = command
            state["fps"]        = round(fps, 1)

        # SocketIO emit every ~100ms
        emit_cnt += 1
        if emit_cnt % 3 == 0:
            socketio.emit('state_update', {
                "gesture":   gesture,
                "confidence": round(confidence, 3),
                "command":   command,
                "fps":       round(fps, 1),
                "car_ready": state["car_ready"],
                "stats":     state["stats"],
            })

    cap.release()
    detector.close()


# ── MJPEG stream ───────────────────────────────────────────────

def generate_frames():
    while True:
        with frame_lock:
            frame = state["frame"]

        if frame is None:
            placeholder = np.zeros((480,640,3), dtype=np.uint8)
            cv2.putText(placeholder, "Camera initializing...",
                        (160,240), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (100,100,100), 2)
            frame = placeholder

        ret, buf = cv2.imencode('.jpg', frame,
                                [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ret:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                   + buf.tobytes() + b'\r\n')
        time.sleep(0.033)


# ── Routes ─────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video')
def video():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    return jsonify({
        "gesture":    state["gesture"],
        "confidence": state["confidence"],
        "command":    state["command"],
        "fps":        state["fps"],
        "car_ready":  state["car_ready"],
    })


# ── Entry point ────────────────────────────────────────────────

if __name__ == '__main__':
    print("═" * 50)
    print("  Gesture Car — Mode A (Laptop)")
    print("═" * 50)

    model, encoder = load_model()
    publisher      = MQTTPublisher()
    publisher.connect()

    print(f"[MQTT] Connecting to {MQTT_BROKER}...")
    time.sleep(2)  # Wait for connection

    t = threading.Thread(
        target=inference_thread,
        args=(model, encoder, publisher),
        daemon=True,
        name="InferenceThread"
    )
    t.start()
    print(f"[SERVER] Dashboard → http://localhost:{FLASK_PORT}")

    try:
        socketio.run(app, host=FLASK_HOST, port=FLASK_PORT,
                     debug=False, use_reloader=False)
    finally:
        publisher.disconnect()