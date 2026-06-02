# ─────────────────────────────────────────────────────────────
# Shared utilities used by collect_data.py, app.py,
# and extract_from_images.py.
#
# Contains:
#   - MediaPipe hand detector builder
#   - Feature extraction and normalization
#   - Frame processing helper
#   - Landmark list extractor
#   - FastVoteBuffer — asymmetric response for car control
# ─────────────────────────────────────────────────────────────

import numpy as np
import mediapipe as mp
from collections import deque


def build_hand_detector(detection_conf: float, tracking_conf: float):
    """
    Initialise and return a MediaPipe Hands object.
    Called once at startup — not per frame.

    Creating per-frame resets tracking state, causing
    full detection every frame instead of fast tracking.
    Always create once, reuse across all frames.
    """
    return mp.solutions.hands.Hands(
        static_image_mode        = False,
        max_num_hands            = 1,
        min_detection_confidence = detection_conf,
        min_tracking_confidence  = tracking_conf,
    )


def extract_features(landmarks) -> np.ndarray:
    """
    Convert 21 MediaPipe landmark objects to 63-dim
    normalized feature vector.

    Normalization — two steps:

    Step 1 — Translation (subtract wrist):
      Landmark 0 is the wrist. Subtract its x,y,z from all
      landmarks. After this, wrist is always at (0,0,0).
      The vector no longer depends on hand position in frame.

    Step 2 — Scale (divide by max absolute value):
      Find the largest absolute value across all 63 numbers.
      Divide everything by it. All values land in [-1, +1].
      The vector no longer depends on hand size or distance
      from camera.

    These two steps together make the vector invariant to
    position AND scale — only gesture shape matters.

    Args:
        landmarks: result.multi_hand_landmarks[0].landmark
                   (list-like of 21 objects with .x .y .z)

    Returns:
        np.ndarray shape (63,) dtype float32, values in [-1,+1]
    """
    if len(landmarks) != 21:
        raise ValueError(
            f"Expected 21 landmarks, got {len(landmarks)}"
        )

    wrist_x = landmarks[0].x
    wrist_y = landmarks[0].y
    wrist_z = landmarks[0].z

    coords = []
    for lm in landmarks:
        coords.append(lm.x - wrist_x)
        coords.append(lm.y - wrist_y)
        coords.append(lm.z - wrist_z)

    coords  = np.array(coords, dtype=np.float32)
    max_val = np.max(np.abs(coords))

    if max_val < 1e-6:
        # Degenerate case: all landmarks collapsed to one point.
        # Happens when MediaPipe loses tracking for one frame.
        # Return zero vector — rejected by confidence gate.
        return np.zeros(63, dtype=np.float32)

    return coords / max_val


def process_frame(frame, detector):
    """
    Run MediaPipe on one BGR frame.

    Args:
        frame:    BGR numpy array from cv2.VideoCapture
        detector: MediaPipe Hands object from build_hand_detector()

    Returns:
        (result, rgb_frame)

    Why convert BGR to RGB:
        OpenCV reads frames as BGR. MediaPipe expects RGB.
        Skipping conversion causes silent accuracy degradation
        on some skin tones — not an error, just wrong colors.

    Why writeable=False:
        Avoids an internal memory copy in MediaPipe.
        Small but consistent performance gain per frame.
    """
    import cv2
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    result = detector.process(rgb)
    rgb.flags.writeable = True
    return result, rgb


def get_landmark_list(result):
    """
    Extract first hand's landmarks from a MediaPipe result.

    Returns landmark list if hand detected, else None.

    Why not just check result.multi_hand_landmarks directly:
        It returns None (not empty list) when no hand found.
        Every caller would need the same None check.
        Centralizing it prevents the inevitable missed check.
    """
    if result.multi_hand_landmarks:
        return result.multi_hand_landmarks[0].landmark
    return None


class FastVoteBuffer:
    """
    Asymmetric vote buffer for real-time RC car control.

    Two different response speeds:

    STOP (1 frame = ~33ms at 30fps):
      Any of these triggers instant STOP:
        - No hand visible in frame
        - Confidence drops below threshold
        - Explicit STOP gesture

    MOTION commands (3 frames = ~100ms at 30fps):
      FORWARD, REVERSE, LEFT, RIGHT require 3 consecutive
      unanimous predictions before firing. This prevents:
        - Single noisy frame from triggering movement
        - Gesture transition frames causing wrong commands
        - Accidental brief gestures while repositioning hand

    Why asymmetric:
      A car that is slow to stop is dangerous.
      A car that is slow to start is just slightly slow.
      The asymmetry is intentional safety design.

    Args:
        confidence_threshold: minimum confidence to accept prediction
    """

    MOTION_VOTES = 3
    MOTION_CMDS  = {"FORWARD", "REVERSE", "LEFT", "RIGHT"}

    def __init__(self, confidence_threshold: float):
        self.buf        = deque(maxlen=self.MOTION_VOTES)
        self.conf_thresh= confidence_threshold
        self.last_stable= "STOP"

    def update(
        self,
        label: str,
        confidence: float,
        hand_present: bool,
    ) -> str:
        """
        Update buffer with new frame result.

        Args:
            label:        classifier output class name (lowercase ok)
            confidence:   classifier probability [0.0, 1.0]
            hand_present: whether MediaPipe found a hand this frame

        Returns:
            Command string: FORWARD | REVERSE | LEFT | RIGHT | STOP
        """
        # Rule 1: No hand → instant STOP
        if not hand_present:
            self.buf.clear()
            self.last_stable = "STOP"
            return "STOP"

        # Rule 2: Low confidence → instant STOP
        if confidence < self.conf_thresh:
            self.buf.clear()
            self.last_stable = "STOP"
            return "STOP"

        cmd = label.upper()

        # Rule 3: STOP gesture → instant STOP
        if cmd == "STOP":
            self.buf.clear()
            self.last_stable = "STOP"
            return "STOP"

        # Rule 4: Motion command → needs MOTION_VOTES consecutive frames
        if cmd in self.MOTION_CMDS:
            self.buf.append(cmd)

            if (len(self.buf) >= self.MOTION_VOTES and
                    all(v == self.buf[0] for v in self.buf)):
                self.last_stable = self.buf[0]
                return self.last_stable

        # Buffer not unanimous yet — hold last stable command
        # Prevents flicker during gesture transitions
        return self.last_stable

    def force_stop(self):
        """Call when camera closes or app shuts down."""
        self.buf.clear()
        self.last_stable = "STOP"