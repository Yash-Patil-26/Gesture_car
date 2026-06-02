# ─────────────────────────────────────────────────────────────
# Mode A — Standalone laptop gesture controller.
# No Flask server. Just webcam window + MQTT commands.
# Lighter than app.py — use for quick testing.
#
# Run: python src/controller.py
# Press Q to quit.
# ─────────────────────────────────────────────────────────────

import cv2
import pickle
import sys
import os
import time
import numpy as np
import paho.mqtt.client as mqtt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mediapipe as mp
from config import (
    MODEL_FILE, ENCODER_FILE,
    CAM_INDEX, CAM_WIDTH, CAM_HEIGHT,
    MP_DETECTION_CONFIDENCE, MP_TRACKING_CONFIDENCE,
    CONFIDENCE_THRESHOLD,
    MQTT_BROKER, MQTT_PORT, MQTT_USER,
    MQTT_PASSWORD, MQTT_TOPIC, MQTT_STATUS
)
from hand_utils import (
    build_hand_detector, process_frame,
    get_landmark_list, extract_features,
    FastVoteBuffer
)

mp_draw         = mp.solutions.drawing_utils
mp_hands_module = mp.solutions.hands

CONTROLLER_ID = "laptop_controller"


# ── Model loader ───────────────────────────────────────────────

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


# ── MQTT command sender ────────────────────────────────────────

class MQTTSender:
    """
    Publishes gesture commands to HiveMQ broker.
    ESP8266 subscribes to same topic and drives motors.

    Deduplication: only publishes when command changes
    or heartbeat interval (400ms) is exceeded.
    This prevents flooding the broker at 30fps.
    """

    HEARTBEAT_S = 0.4

    def __init__(self):
        self.client    = mqtt.Client(
            client_id     = CONTROLLER_ID,
            clean_session = True
        )
        self.client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        self.client.tls_set()   # HiveMQ requires TLS

        self.connected   = False
        self.car_ready   = False
        self.last_cmd    = None
        self.last_sent   = 0

        self.client.on_connect    = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message    = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            client.subscribe(MQTT_STATUS)
            # Claim the car
            client.publish(
                MQTT_TOPIC,
                f"{CONTROLLER_ID}:CONNECT",
                qos=0
            )
            print("[MQTT] Connected to broker")
            print("[MQTT] Waiting for car to respond...")
        else:
            print(f"[MQTT] Connection refused: rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        self.car_ready = False
        print("[MQTT] Disconnected from broker")

    def _on_message(self, client, userdata, msg):
        m = msg.payload.decode()
        if f"READY:{CONTROLLER_ID}" in m:
            self.car_ready = True
            print("[MQTT] Car is ready — you can start gesturing")
        elif "BUSY" in m:
            self.car_ready = False
            print("[MQTT] Car is busy — another controller is active")
        elif m == "FREE":
            self.car_ready = False

    def connect(self):
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
            self.client.loop_start()
            print(f"[MQTT] Connecting to {MQTT_BROKER}...")
        except Exception as e:
            print(f"[MQTT] Failed to connect: {e}")

    def send(self, command: str):
        """
        Publish command to MQTT topic.
        Only sends when command changes or heartbeat fires.
        Silently skips if not connected or car not ready.
        """
        if not self.connected or not self.car_ready:
            return

        now     = time.time()
        changed = command != self.last_cmd
        beat    = now - self.last_sent > self.HEARTBEAT_S

        if changed or beat:
            payload = f"{CONTROLLER_ID}:{command}"
            self.client.publish(MQTT_TOPIC, payload, qos=0)
            self.last_cmd  = command
            self.last_sent = now

    def disconnect(self):
        if self.connected:
            self.client.publish(
                MQTT_TOPIC,
                f"{CONTROLLER_ID}:DISCONNECT",
                qos=0
            )
            self.client.publish(
                MQTT_TOPIC,
                f"{CONTROLLER_ID}:STOP",
                qos=0
            )
        self.client.loop_stop()
        self.client.disconnect()


# ── HUD overlay ────────────────────────────────────────────────

def draw_hud(frame, label, confidence, command, fps, car_ready):
    h, w = frame.shape[:2]

    # Top bar
    cv2.rectangle(frame, (0, 0), (w, 90), (18, 18, 18), -1)

    # Gesture label
    color = (0, 220, 100) if confidence >= CONFIDENCE_THRESHOLD \
            else (80, 80, 220)
    cv2.putText(frame, f"Gesture: {label}",
                (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2)

    # Confidence bar
    bar_w = int(confidence * 200)
    cv2.rectangle(frame, (16, 50), (216, 66), (50, 50, 50), -1)
    cv2.rectangle(frame, (16, 50), (16 + bar_w, 66), color, -1)
    cv2.putText(frame, f"{confidence:.0%}",
                (224, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                (180, 180, 180), 1)

    # Active command
    cmd_color = {
        "FORWARD": (0, 220, 100),
        "REVERSE": (77, 171, 247),
        "LEFT":    (179, 157, 219),
        "RIGHT":   (255, 179, 0),
        "STOP":    (255, 82, 82),
    }.get(command, (200, 200, 200))

    cv2.putText(frame, command,
                (w - 180, 56), cv2.FONT_HERSHEY_SIMPLEX,
                1.1, cmd_color, 2)

    # Bottom bar
    cv2.rectangle(frame, (0, h - 30), (w, h), (18, 18, 18), -1)

    # Car status
    car_color = (0, 220, 100) if car_ready else (255, 82, 82)
    car_text  = "Car: READY" if car_ready else "Car: waiting..."
    cv2.putText(frame, car_text,
                (16, h - 9), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, car_color, 1)

    # FPS
    cv2.putText(frame, f"FPS: {fps:.1f}",
                (w - 100, h - 9), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, (140, 140, 140), 1)


# ── Main ───────────────────────────────────────────────────────

def main():
    print("═" * 52)
    print("  Gesture Car — Mode A Controller (standalone)")
    print("═" * 52)

    model, encoder = load_model()
    detector       = build_hand_detector(
        MP_DETECTION_CONFIDENCE,
        MP_TRACKING_CONFIDENCE
    )

    sender   = MQTTSender()
    sender.connect()

    # Give broker 2 seconds to connect before opening camera
    print("[WAIT] Connecting to broker...")
    time.sleep(2)

    vote_buf = FastVoteBuffer(CONFIDENCE_THRESHOLD)

    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          30)

    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera {CAM_INDEX}")
        print("Change CAM_INDEX in config.py and try again.")
        sender.disconnect()
        return

    print("\n[CAM] Camera opened")
    print("[INFO] Press Q to quit\n")

    fps    = 0.0
    t_prev = time.time()
    label  = "—"
    confidence = 0.0
    command    = "STOP"

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        frame     = cv2.flip(frame, 1)
        result, _ = process_frame(frame, detector)
        lms       = get_landmark_list(result)

        if lms is not None:
            # Draw skeleton
            mp_draw.draw_landmarks(
                frame,
                result.multi_hand_landmarks[0],
                mp_hands_module.HAND_CONNECTIONS,
                mp_draw.DrawingSpec(
                    color=(0, 180, 255),
                    thickness=2,
                    circle_radius=3
                ),
                mp_draw.DrawingSpec(
                    color=(255, 255, 255),
                    thickness=1
                )
            )

            # Classify
            features   = extract_features(lms).reshape(1, -1)
            proba      = model.predict_proba(features)[0]
            class_idx  = int(np.argmax(proba))
            confidence = float(proba[class_idx])
            label      = encoder.classes_[class_idx]

            # Vote → command
            command = vote_buf.update(label, confidence, True)

        else:
            command    = vote_buf.update("stop", 0.0, False)
            label      = "No hand"
            confidence = 0.0

        # Send via MQTT
        sender.send(command)

        # FPS
        t_now  = time.time()
        fps    = 0.9 * fps + 0.1 * (1.0 / max(t_now - t_prev, 1e-6))
        t_prev = t_now

        draw_hud(frame, label, confidence, command, fps, sender.car_ready)
        cv2.imshow("Gesture Car — Mode A", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Cleanup
    print("\n[EXIT] Stopping...")
    sender.send("STOP")
    time.sleep(0.3)
    sender.disconnect()
    cap.release()
    cv2.destroyAllWindows()
    detector.close()
    print("[EXIT] Done.")


if __name__ == "__main__":
    main()