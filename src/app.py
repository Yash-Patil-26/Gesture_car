# src/app.py
# ─────────────────────────────────────────────────────────────
# Flask backend server — LAPTOP MODE for development/testing.
# Runs MediaPipe + ML inference locally on laptop.
# Sends commands to ESP8266 via HiveMQ MQTT broker.
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

# Verify paho-mqtt is installed
try:
    import paho.mqtt.client as paho_mqtt
except ImportError:
    print("\n" + "!"*55)
    print("  ERROR: paho-mqtt not installed.")
    print("  Run: pip install paho-mqtt==1.6.1")
    print("!"*55 + "\n")
    sys.exit(1)

from flask import Flask, Response, render_template, jsonify
from flask_socketio import SocketIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    MODEL_FILE, ENCODER_FILE,
    CAM_INDEX, CAM_WIDTH, CAM_HEIGHT,
    MP_DETECTION_CONFIDENCE, MP_TRACKING_CONFIDENCE,
    CONFIDENCE_THRESHOLD, VOTE_WINDOW,
    FLASK_HOST, FLASK_PORT,
    GESTURES,
    MQTT_BROKER, MQTT_PORT_TLS,
    MQTT_USERNAME, MQTT_PASSWORD,
    MQTT_TOPIC_CMD, MQTT_TOPIC_STATUS,
)
from hand_utils import (
    build_hand_detector, process_frame,
    get_landmark_list, extract_features, FastVoteBuffer,
)

# ── Flask + SocketIO ──────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder = os.path.join(BASE_DIR, "templates"),
    static_folder   = os.path.join(BASE_DIR, "static"),
)
app.config['SECRET_KEY'] = 'gesture_car_dev_2024'
socketio = SocketIO(
    app,
    cors_allowed_origins = "*",
    async_mode          = 'threading',
    logger              = False,
    engineio_logger     = False,
)

# ── Shared state ──────────────────────────────────────────────
frame_lock = threading.Lock()
state = {
    "frame":         None,
    "gesture":       "—",
    "confidence":    0.0,
    "command":       "STOP",
    "car_connected": False,
    "cam_connected": False,
    "fps":           0.0,
    "session_stats": {g: 0 for g in GESTURES},
    "last_commands": [],
}


# ── MQTT sender ───────────────────────────────────────────────
class MQTTSender:
    """
    Sends commands to ESP8266 via HiveMQ MQTT broker.
    Connects over TLS port 8883.
    """

    def __init__(self):
        self.connected  = False
        self.last_cmd   = None
        self.last_sent  = 0.0

        # Validate config before connecting
        if "xxxxxxxx" in MQTT_BROKER:
            print("\n" + "!"*55)
            print("  WARNING: MQTT_BROKER not configured in config.py")
            print("  Update MQTT_BROKER with your HiveMQ cluster URL")
            print("  Car will not receive commands until this is set")
            print("!"*55 + "\n")
            return

        self.client = paho_mqtt.Client(
            client_id = "gesture_laptop_dev",
            protocol  = paho_mqtt.MQTTv311,
        )
        self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        # TLS for port 8883
        try:
            self.client.tls_set()
        except Exception as e:
            print(f"[MQTT] TLS setup error: {e}")
            return

        self.client.on_connect    = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish    = self._on_publish

        try:
            print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT_TLS}")
            self.client.connect(MQTT_BROKER, MQTT_PORT_TLS, keepalive=30)
            self.client.loop_start()
        except Exception as e:
            print(f"[MQTT] Connection failed: {e}")
            print("[MQTT] Check: internet connection, broker URL, credentials")

    def _on_connect(self, client, userdata, flags, rc):
        rc_meanings = {
            0: "Connected successfully",
            1: "Wrong protocol version",
            2: "Invalid client ID",
            3: "Broker unavailable",
            4: "Wrong username or password",
            5: "Not authorised",
        }
        if rc == 0:
            self.connected = True
            print(f"[MQTT] ✓ Connected to HiveMQ")
            # Subscribe to car status to confirm car is online
            self.client.subscribe(MQTT_TOPIC_STATUS)
        else:
            self.connected = False
            meaning = rc_meanings.get(rc, f"Unknown error rc={rc}")
            print(f"[MQTT] ✗ Connection refused: {meaning}")
            if rc == 4:
                print("[MQTT] Check MQTT_USERNAME and MQTT_PASSWORD in config.py")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            print(f"[MQTT] Unexpected disconnect rc={rc} — will auto-reconnect")
        else:
            print("[MQTT] Disconnected cleanly")

    def _on_publish(self, client, userdata, mid):
        pass  # called when message delivered

    def send(self, command: str):
        if not hasattr(self, 'client') or not self.connected:
            return

        now       = time.time()
        changed   = command != self.last_cmd
        heartbeat = now - self.last_sent > 0.4

        if changed or heartbeat:
            try:
                result = self.client.publish(
                    MQTT_TOPIC_CMD, command, qos=0, retain=False)
                if result.rc == paho_mqtt.MQTT_ERR_SUCCESS:
                    self.last_cmd  = command
                    self.last_sent = now
            except Exception as e:
                print(f"[MQTT] Publish error: {e}")

    def close(self):
        if hasattr(self, 'client'):
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass


# ── Model loader ──────────────────────────────────────────────
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


# ── Frame annotation ──────────────────────────────────────────
mp_draw      = mp.solutions.drawing_utils
mp_hands_mod = mp.solutions.hands

COMMAND_COLORS = {
    "FORWARD": (0,  220, 100),
    "REVERSE": (0,  120, 255),
    "LEFT":    (200,100, 255),
    "RIGHT":   (255,180, 0),
    "STOP":    (60, 60,  220),
}

def annotate_frame(frame, gesture, confidence, command, mqtt_connected):
    h, w      = frame.shape[:2]
    cmd_color = COMMAND_COLORS.get(command, (200, 200, 200))

    # Top bar
    cv2.rectangle(frame, (0, 0), (w, 90), (18, 18, 18), -1)

    # Gesture
    conf_color = (0,220,100) if confidence >= CONFIDENCE_THRESHOLD \
                             else (80,80,220)
    cv2.putText(frame, f"Gesture: {gesture}",
                (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.85, conf_color, 2)

    # Confidence bar
    bar_w = int(confidence * 200)
    cv2.rectangle(frame, (16, 50), (216, 66), (50,50,50), -1)
    cv2.rectangle(frame, (16, 50), (16+bar_w, 66), conf_color, -1)
    cv2.putText(frame, f"{confidence:.0%}",
                (224, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (180,180,180), 1)

    # Command
    cv2.putText(frame, command,
                (w-180, 56), cv2.FONT_HERSHEY_SIMPLEX, 1.1, cmd_color, 2)

    # Bottom bar — show MQTT status
    cv2.rectangle(frame, (0, h-28), (w, h), (18,18,18), -1)
    mqtt_text  = "MQTT: HiveMQ ✓" if mqtt_connected else "MQTT: connecting..."
    mqtt_color = (0,200,100) if mqtt_connected else (100,100,255)
    cv2.putText(frame, f"LAPTOP MODE  |  {mqtt_text}",
                (16, h-8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, mqtt_color, 1)

    return frame


# ── Inference thread ──────────────────────────────────────────
def inference_thread(model, encoder):
    detector    = build_hand_detector(
        MP_DETECTION_CONFIDENCE, MP_TRACKING_CONFIDENCE)
    sender      = MQTTSender()
    vote_buf    = FastVoteBuffer(CONFIDENCE_THRESHOLD)

    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          30)

    state["cam_connected"] = cap.isOpened()
    if not cap.isOpened():
        print(f"[CAM] ERROR: Cannot open camera index {CAM_INDEX}")
        print("Change CAM_INDEX in config.py")
        return

    print(f"[CAM] Opened {CAM_WIDTH}×{CAM_HEIGHT}")

    fps          = 0.0
    t_prev       = time.time()
    gesture      = "—"
    confidence   = 0.0
    command      = "STOP"
    emit_counter = 0

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
                mp_hands_mod.HAND_CONNECTIONS,
                mp_draw.DrawingSpec(color=(0,180,255), thickness=2, circle_radius=3),
                mp_draw.DrawingSpec(color=(255,255,255), thickness=1),
            )
            features   = extract_features(lms).reshape(1, -1)
            proba      = model.predict_proba(features)[0]
            idx        = int(np.argmax(proba))
            confidence = float(proba[idx])
            gesture    = encoder.classes_[idx]
        else:
            gesture    = "No hand"
            confidence = 0.0

        command = vote_buf.update(gesture, confidence, lms is not None)
        sender.send(command)

        # Update session stats
        if command in state["session_stats"]:
            state["session_stats"][command] += 1

        # Rolling command log
        log = state["last_commands"]
        log.append({
            "cmd":  command,
            "time": time.strftime("%H:%M:%S"),
            "conf": round(confidence, 3),
        })
        if len(log) > 20:
            log.pop(0)

        # FPS
        t_now  = time.time()
        fps    = 0.9 * fps + 0.1 * (1.0 / max(t_now - t_prev, 1e-6))
        t_prev = t_now

        # Annotate
        display = annotate_frame(
            frame.copy(), gesture, confidence,
            command, sender.connected
        )

        with frame_lock:
            state["frame"]         = display
            state["gesture"]       = gesture
            state["confidence"]    = round(confidence, 3)
            state["command"]       = command
            state["fps"]           = round(fps, 1)
            state["car_connected"] = sender.connected

        # Emit to browser ~10 Hz
        emit_counter += 1
        if emit_counter % 3 == 0:
            socketio.emit('state_update', {
                "gesture":    gesture,
                "confidence": round(confidence, 3),
                "command":    command,
                "fps":        round(fps, 1),
                "car":        sender.connected,
                "stats":      state["session_stats"],
                "log":        state["last_commands"][-5:],
            })

    cap.release()
    detector.close()
    sender.close()


# ── MJPEG stream ──────────────────────────────────────────────
def generate_frames():
    while True:
        with frame_lock:
            frame = state["frame"]

        if frame is None:
            placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(placeholder, "Camera initializing…",
                        (140, 240), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (100,100,100), 2)
            frame = placeholder

        ret, buf = cv2.imencode(
            '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ret:
            continue

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n'
            + buf.tobytes()
            + b'\r\n'
        )
        time.sleep(0.033)


# ── Flask routes ──────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video')
def video():
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
    )

@app.route('/status')
def status():
    return jsonify({
        "gesture":    state["gesture"],
        "confidence": state["confidence"],
        "command":    state["command"],
        "fps":        state["fps"],
        "car":        state["car_connected"],
        "cam":        state["cam_connected"],
        "stats":      state["session_stats"],
        "log":        state["last_commands"],
    })

@app.route('/ping')
def ping():
    return jsonify({"ok": True, "time": time.strftime("%H:%M:%S")})


# ── SocketIO events ───────────────────────────────────────────
@socketio.on('connect')
def on_ws_connect():
    print(f"[WS] Browser connected")

@socketio.on('disconnect')
def on_ws_disconnect():
    print(f"[WS] Browser disconnected")


# ── Entry point ───────────────────────────────────────────────
if __name__ == '__main__':
    print("═" * 55)
    print("  Gesture Car — Laptop Development Mode")
    print("═" * 55)
    print(f"  MQTT Broker : {MQTT_BROKER}")
    print(f"  MQTT Topic  : {MQTT_TOPIC_CMD}")
    print(f"  Camera      : index {CAM_INDEX}")
    print("─" * 55)

    model, encoder = load_model()

    t = threading.Thread(
        target   = inference_thread,
        args     = (model, encoder),
        daemon   = True,
        name     = "InferenceThread",
    )
    t.start()
    print(f"[THREAD] Inference thread started")
    print(f"[SERVER] Open in browser: http://localhost:{FLASK_PORT}")
    print("─" * 55)

    socketio.run(
        app,
        host         = FLASK_HOST,
        port         = FLASK_PORT,
        debug        = False,
        use_reloader = False,
        allow_unsafe_werkzeug = True,
    )