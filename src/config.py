import os

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR     = os.path.join(BASE_DIR, "data")
MODEL_DIR    = os.path.join(BASE_DIR, "model")
OUTPUT_DIR   = os.path.join(BASE_DIR, "outputs")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR   = os.path.join(BASE_DIR, "static")

DATA_CSV     = os.path.join(DATA_DIR,   "gesture_data.csv")
MODEL_FILE   = os.path.join(MODEL_DIR,  "gesture_model.pkl")
ENCODER_FILE = os.path.join(MODEL_DIR,  "label_encoder.pkl")
CM_IMAGE     = os.path.join(OUTPUT_DIR, "confusion_matrix.png")

# ── Gestures ───────────────────────────────────────────────────
GESTURES            = ["forward", "reverse", "left", "right", "stop"]
SAMPLES_PER_GESTURE = 200

# ── MediaPipe ──────────────────────────────────────────────────
NUM_LANDMARKS           = 21
FEATURES_PER_LANDMARK   = 3
FEATURE_DIM             = NUM_LANDMARKS * FEATURES_PER_LANDMARK  # 63
MP_DETECTION_CONFIDENCE = 0.7
MP_TRACKING_CONFIDENCE  = 0.6

# ── Camera ─────────────────────────────────────────────────────
CAM_INDEX  = 0
CAM_WIDTH  = 640
CAM_HEIGHT = 480
CAM_FPS    = 30

# ── Training ───────────────────────────────────────────────────
TEST_SIZE           = 0.2
RANDOM_STATE        = 42
CV_FOLDS            = 5
RF_N_ESTIMATORS     = 100
RF_MIN_SAMPLES_LEAF = 2
MLP_HIDDEN_LAYERS   = (128, 64)
MLP_MAX_ITER        = 500

# ── Inference ──────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.85
VOTE_WINDOW          = 5

# ── MQTT (HiveMQ Cloud) ────────────────────────────────────────
# Credentials match firmware exactly — read from here by app.py and controller.py
MQTT_BROKER   = "29455b01c27447b488b1ec93488ce95d.s1.eu.hivemq.cloud"
MQTT_PORT     = 8883
MQTT_USER     = "gesturecar"
MQTT_PASSWORD = "#Yash@2026"
MQTT_TOPIC    = "gesture/car/command"
MQTT_STATUS   = "gesture/car/status"

# ── Flask ──────────────────────────────────────────────────────
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000