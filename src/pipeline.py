# Unified ML pipeline — runs all 4 stages in sequence:
#   1. filter    — score and keep best images per gesture
#   2. extract   — MediaPipe landmarks → CSV
#   3. train     — Random Forest classifier
#   4. export    — sklearn model → ONNX for browser

import os
import sys
import csv
import json
import time
import pickle
import random
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import mediapipe as mp

from collections import deque
from dataclasses import dataclass

from sklearn.ensemble        import RandomForestClassifier
from sklearn.neural_network  import MLPClassifier
from sklearn.preprocessing   import LabelEncoder
from sklearn.model_selection import (
    train_test_split, cross_val_score, StratifiedKFold
)
from sklearn.metrics import classification_report, confusion_matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    GESTURES, DATA_CSV, DATA_DIR, MODEL_DIR, OUTPUT_DIR, DOCS_DIR,
    MODEL_FILE, ENCODER_FILE, CM_IMAGE,
    FEATURE_DIM, MP_DETECTION_CONFIDENCE,
    TEST_SIZE, RANDOM_STATE, CV_FOLDS,
    RF_N_ESTIMATORS, RF_MIN_SAMPLES_LEAF,
    MLP_HIDDEN_LAYERS, MLP_MAX_ITER,
    CONFIDENCE_THRESHOLD,
)
from config import extract_features   # shared with app.py

# ═══════════════════════════════════════════════════════════════
# STAGE 1 — FILTER
# Score every image on 4 quality metrics.
# Keep top KEEP_PER_GESTURE per gesture. Delete the rest.
# ═══════════════════════════════════════════════════════════════

KEEP_PER_GESTURE = 3500
MIN_DETECT_CONF  = 0.5
SUPPORTED_EXT    = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}

# Scoring weights — must sum to 1.0
W_AREA, W_CONF, W_SPREAD, W_CENTER = 0.35, 0.30, 0.20, 0.15

IMAGE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "external_images"
)


@dataclass
class ImageScore:
    path:     str
    score:    float
    detected: bool


def _score_image(img_path: str, detector) -> ImageScore:
    import cv2
    img = cv2.imread(img_path)
    if img is None:
        return ImageScore(img_path, 0.0, False)

    rgb    = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    result = detector.process(rgb)

    if not result.multi_hand_landmarks or len(result.multi_hand_landmarks) != 1:
        return ImageScore(img_path, 0.0, False)

    lms = result.multi_hand_landmarks[0].landmark
    xs  = [l.x for l in lms]; ys = [l.y for l in lms]

    area_score = min((max(xs)-min(xs)) * (max(ys)-min(ys)) / 0.25, 1.0)

    conf_score = 0.0
    if result.multi_handedness:
        conf_score = result.multi_handedness[0].classification[0].score

    wx, wy, wz = lms[0].x, lms[0].y, lms[0].z
    devs = []
    for lm in lms:
        devs.extend([lm.x-wx, lm.y-wy, lm.z-wz])
    spread_score = min(max(abs(v) for v in devs) / 0.30, 1.0)

    centrality_score = min(
        min(lms[0].x, 1-lms[0].x, lms[0].y, 1-lms[0].y) / 0.20, 1.0)

    score = (W_AREA*area_score + W_CONF*conf_score +
             W_SPREAD*spread_score + W_CENTER*centrality_score)

    return ImageScore(img_path, round(score, 4), True)


def stage_filter(dry_run: bool = False):
    print("\n" + "═"*55)
    print("  STAGE 1 — IMAGE FILTER")
    print("  Keep:", KEEP_PER_GESTURE, "per gesture")
    print("  Mode:", "DRY RUN" if dry_run else "LIVE (will delete)")
    print("═"*55)

    if not os.path.exists(IMAGE_ROOT):
        print(f"  ERROR: {IMAGE_ROOT} not found — skipping filter")
        return

    detector = mp.solutions.hands.Hands(
        static_image_mode=True, max_num_hands=2,
        min_detection_confidence=MIN_DETECT_CONF, model_complexity=1)

    total_freed = 0
    for gesture in GESTURES:
        folder = os.path.join(IMAGE_ROOT, gesture)
        if not os.path.exists(folder): continue

        files = [
            os.path.join(folder, fn) for fn in os.listdir(folder)
            if os.path.splitext(fn)[1].lower() in SUPPORTED_EXT
        ]
        if not files: continue

        print(f"\n  '{gesture}': scoring {len(files):,} images…")
        random.shuffle(files)
        scores = [_score_image(fp, detector) for fp in files]
        scores.sort(key=lambda x: x.score, reverse=True)

        keep  = {s.path for s in scores if s.detected}
        keep  = set(list(keep)[:KEEP_PER_GESTURE])
        dels  = [s for s in scores if s.path not in keep]

        freed = 0
        for s in dels:
            if not dry_run:
                try:
                    freed += os.path.getsize(s.path)
                    os.remove(s.path)
                except OSError: pass
            else:
                try: freed += os.path.getsize(s.path)
                except OSError: pass

        total_freed += freed
        print(f"  kept={min(len(keep),KEEP_PER_GESTURE):,}  "
              f"deleted={len(dels):,}  freed={freed/1e6:.1f}MB")

    detector.close()
    print(f"\n  Total freed: {total_freed/1e6:.1f}MB")
    print(f"  {'DRY RUN — nothing deleted' if dry_run else 'Complete'}")


# ═══════════════════════════════════════════════════════════════
# STAGE 2 — EXTRACT
# Run MediaPipe on every filtered image → append to CSV.
# ═══════════════════════════════════════════════════════════════

def _init_csv():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_CSV):
        with open(DATA_CSV, 'w', newline='') as f:
            csv.writer(f).writerow(
                ['label'] + [f'f{i}' for i in range(FEATURE_DIM)])
        print(f"  Created: {DATA_CSV}")
    else:
        print(f"  Appending to: {DATA_CSV}")


def stage_extract():
    import cv2
    print("\n" + "═"*55)
    print("  STAGE 2 — LANDMARK EXTRACTION")
    print("═"*55)

    _init_csv()

    detector = mp.solutions.hands.Hands(
        static_image_mode=True, max_num_hands=1,
        min_detection_confidence=0.5, model_complexity=1)

    total_saved = 0
    with open(DATA_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        for gesture in GESTURES:
            folder = os.path.join(IMAGE_ROOT, gesture)
            if not os.path.exists(folder):
                print(f"\n  [SKIP] {folder}")
                continue

            files = [
                os.path.join(folder, fn) for fn in os.listdir(folder)
                if os.path.splitext(fn)[1].lower() in SUPPORTED_EXT
            ]
            saved = 0; skipped = 0
            print(f"\n  '{gesture}': {len(files):,} images…")
            t0 = time.time()

            for fp in files:
                img = cv2.imread(fp)
                if img is None: skipped += 1; continue
                rgb    = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                result = detector.process(rgb)
                if not result.multi_hand_landmarks: skipped += 1; continue
                lms      = result.multi_hand_landmarks[0].landmark
                features = extract_features(lms)
                writer.writerow([gesture] + features.tolist())
                saved += 1

            total_saved += saved
            print(f"  saved={saved:,}  skipped={skipped}  "
                  f"time={time.time()-t0:.0f}s")
        f.flush()

    detector.close()
    print(f"\n  Total saved: {total_saved:,} rows → {DATA_CSV}")


# ═══════════════════════════════════════════════════════════════
# STAGE 3 — TRAIN
# Load CSV → Random Forest → evaluate → save .pkl
# ═══════════════════════════════════════════════════════════════

def stage_train():
    print("\n" + "═"*55)
    print("  STAGE 3 — TRAINING")
    print("═"*55)

    if not os.path.exists(DATA_CSV):
        print(f"  ERROR: {DATA_CSV} not found — run extract first")
        return None, None

    df = pd.read_csv(DATA_CSV)
    print(f"  Rows: {len(df):,}  Classes: {sorted(df['label'].unique())}")

    for cls in GESTURES:
        if cls not in df['label'].values:
            print(f"  WARNING: '{cls}' missing from dataset")

    if df.isnull().any().any():
        raise ValueError("Dataset contains NaN — re-check collect or extract")

    X = df.drop('label', axis=1).values.astype(np.float32)
    y = df['label'].values

    le        = LabelEncoder()
    y_enc     = le.fit_transform(y)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y_enc, test_size=TEST_SIZE, random_state=RANDOM_STATE,
        stratify=y_enc)

    print(f"\n  Train: {len(X_tr):,}   Test: {len(X_te):,}")

    rf  = RandomForestClassifier(
        n_estimators=RF_N_ESTIMATORS, min_samples_leaf=RF_MIN_SAMPLES_LEAF,
        max_features='sqrt', random_state=RANDOM_STATE, n_jobs=-1)
    mlp = MLPClassifier(
        hidden_layer_sizes=MLP_HIDDEN_LAYERS, activation='relu',
        max_iter=MLP_MAX_ITER, random_state=RANDOM_STATE)

    skf = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True,
                          random_state=RANDOM_STATE)

    print(f"\n  {CV_FOLDS}-fold CV:")
    for name, model in [('RandomForest', rf), ('MLP', mlp)]:
        scores = cross_val_score(model, X, y_enc, cv=skf)
        print(f"  {name:15s}: {scores.mean():.4f} ± {scores.std():.4f}")

    print("\n  Training final model…")
    rf.fit(X_tr, y_tr)
    y_pred = rf.predict(X_te)

    print("\n" + classification_report(y_te, y_pred, target_names=le.classes_))

    # Confusion matrix
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cm = confusion_matrix(y_te, y_pred)
    plt.figure(figsize=(7, 5))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=le.classes_, yticklabels=le.classes_)
    plt.title("Confusion Matrix — Gesture Classifier")
    plt.ylabel("True"); plt.xlabel("Predicted")
    plt.tight_layout(); plt.savefig(CM_IMAGE, dpi=150); plt.close()
    print(f"  Confusion matrix → {CM_IMAGE}")

    # Save
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(MODEL_FILE,   'wb') as f: pickle.dump(rf, f)
    with open(ENCODER_FILE, 'wb') as f: pickle.dump(le, f)
    print(f"  Model   → {MODEL_FILE}")
    print(f"  Encoder → {ENCODER_FILE}")

    return rf, le


# ═══════════════════════════════════════════════════════════════
# STAGE 4 — EXPORT
# sklearn Random Forest → ONNX opset 12 → docs/
# ═══════════════════════════════════════════════════════════════

def stage_export():
    print("\n" + "═"*55)
    print("  STAGE 4 — EXPORT TO ONNX")
    print("═"*55)

    try:
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType
    except ImportError:
        print("  Installing skl2onnx…")
        os.system("pip install skl2onnx onnx")
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType

    if not os.path.exists(MODEL_FILE):
        print(f"  ERROR: {MODEL_FILE} not found — run train first")
        return

    with open(MODEL_FILE,   'rb') as f: model   = pickle.load(f)
    with open(ENCODER_FILE, 'rb') as f: encoder = pickle.load(f)

    os.makedirs(DOCS_DIR, exist_ok=True)
    onnx_path   = os.path.join(DOCS_DIR, "model.onnx")
    labels_path = os.path.join(DOCS_DIR, "labels.json")

    onnx_model = convert_sklearn(
        model,
        initial_types = [('float_input', FloatTensorType([None, 63]))],
        target_opset  = 12,
    )
    with open(onnx_path, 'wb') as f:
        f.write(onnx_model.SerializeToString())

    with open(labels_path, 'w') as f:
        json.dump({
            "labels":      list(encoder.classes_),
            "id_to_label": {str(i): c for i, c in enumerate(encoder.classes_)},
        }, f, indent=2)

    size_mb = os.path.getsize(onnx_path) / 1e6
    print(f"  model.onnx  → {onnx_path}  ({size_mb:.1f} MB)")
    print(f"  labels.json → {labels_path}")
    print(f"  Classes     : {list(encoder.classes_)}")
    print(f"\n  Next: git add docs/ && git push")


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Gesture Car ML Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/pipeline.py                     # full pipeline
  python src/pipeline.py --stage filter      # filter only
  python src/pipeline.py --stage train,export # train then export
  python src/pipeline.py --stage filter --dry-run
  python src/pipeline.py --yes               # skip all prompts
        """
    )
    parser.add_argument(
        '--stage',
        default='filter,extract,train,export',
        help='Comma-separated stages: filter,extract,train,export'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Filter stage: score images but do not delete'
    )
    parser.add_argument(
        '--yes', '-y', action='store_true',
        help='Skip all confirmation prompts'
    )
    args = parser.parse_args()

    stages = [s.strip().lower() for s in args.stage.split(',')]
    valid  = {'filter', 'extract', 'train', 'export'}
    bad    = set(stages) - valid
    if bad:
        print(f"Unknown stages: {bad}. Valid: {valid}")
        sys.exit(1)

    print("═"*55)
    print("  Gesture Car — ML Pipeline")
    print(f"  Stages: {', '.join(stages)}")
    print("═"*55)

    # Safety confirmation for filter (deletes files)
    if 'filter' in stages and not args.dry_run and not args.yes:
        print("\n  WARNING: filter stage PERMANENTLY DELETES images.")
        print("  Use --dry-run to preview first.")
        confirm = input("  Type YES to continue: ").strip()
        if confirm != 'YES':
            print("  Cancelled.")
            sys.exit(0)

    t_total = time.time()

    if 'filter'  in stages: stage_filter(dry_run=args.dry_run)
    if 'extract' in stages: stage_extract()
    if 'train'   in stages: stage_train()
    if 'export'  in stages: stage_export()

    print(f"\n{'═'*55}")
    print(f"  Pipeline complete — {time.time()-t_total:.0f}s total")
    print("═"*55)


if __name__ == "__main__":
    main()



