# ─────────────────────────────────────────────────────────────
# ONE-TIME IMAGE QUALITY FILTER.
#
# Scans all images in external_images/ exactly once.
# Scores every image on 4 quality metrics.
# Keeps the top KEEP_PER_GESTURE best images per folder.
# PERMANENTLY DELETES the rest from disk.
#
# Run ONCE before extract_from_images.py:
#   python src/filter_images.py --dry-run   (preview only)
#   python src/filter_images.py             (execute delete)
# ─────────────────────────────────────────────────────────────

import cv2
import os
import sys
import time
import random
import numpy as np
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import GESTURES

import mediapipe as mp

# ── Configuration ──────────────────────────────────────────────
KEEP_PER_GESTURE = 3500     # images to keep per gesture folder
MIN_DETECT_CONF  = 0.5      # below this → score zero
SUPPORTED_EXT    = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}

# Scoring weights — must sum to 1.0
W_AREA       = 0.35   # hand fills enough of image
W_CONFIDENCE = 0.30   # MediaPipe detection confidence
W_SPREAD     = 0.20   # landmark vector richness
W_CENTRALITY = 0.15   # wrist not at image edge

IMAGE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "external_images"
)


@dataclass
class ImageScore:
    path:     str
    score:    float   # 0.0–1.0, higher = better quality
    detected: bool    # whether a hand was found


def score_image(img_path: str, detector) -> ImageScore:
    """
    Score one image on 4 quality metrics.
    Returns composite score in [0, 1].
    Score = 0.0 if no hand detected.

    Metric 1 — Hand area (weight 0.35):
      Bounding box of all 21 landmarks as fraction of image.
      Normalized: 0.25 = full score. Larger hand = better landmarks.

    Metric 2 — Detection confidence (weight 0.30):
      MediaPipe's own internal confidence. Already [0,1].

    Metric 3 — Landmark spread (weight 0.20):
      Max deviation of any landmark from wrist.
      Higher = more finger movement = richer gesture info.

    Metric 4 — Wrist centrality (weight 0.15):
      Wrist distance from nearest frame edge.
      Wrist at center = 1.0. At edge = 0.0.
    """
    img = cv2.imread(img_path)
    if img is None:
        return ImageScore(path=img_path, score=0.0, detected=False)

    img_h, img_w = img.shape[:2]
    rgb    = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    result = detector.process(rgb)

    if (result.multi_hand_landmarks is None or
            len(result.multi_hand_landmarks) == 0):
        return ImageScore(path=img_path, score=0.0, detected=False)

    if len(result.multi_hand_landmarks) > 1:
        return ImageScore(path=img_path, score=0.0, detected=False)

    lms = result.multi_hand_landmarks[0].landmark

    # Metric 1: hand area
    xs    = [lm.x for lm in lms]
    ys    = [lm.y for lm in lms]
    area  = (max(xs) - min(xs)) * (max(ys) - min(ys))
    area_score = min(area / 0.25, 1.0)

    # Metric 2: detection confidence
    conf_score = 0.0
    if result.multi_handedness:
        conf_score = result.multi_handedness[0].classification[0].score

    # Metric 3: landmark spread
    wrist_x = lms[0].x
    wrist_y = lms[0].y
    wrist_z = lms[0].z
    devs    = []
    for lm in lms:
        devs.extend([lm.x - wrist_x, lm.y - wrist_y, lm.z - wrist_z])
    max_dev      = max(abs(v) for v in devs) if devs else 0.0
    spread_score = min(max_dev / 0.30, 1.0)

    # Metric 4: wrist centrality
    wx = lms[0].x
    wy = lms[0].y
    dist_from_edge = min(wx, 1.0 - wx, wy, 1.0 - wy)
    centrality_score = min(dist_from_edge / 0.20, 1.0)

    # Composite
    composite = (
        W_AREA       * area_score       +
        W_CONFIDENCE * conf_score       +
        W_SPREAD     * spread_score     +
        W_CENTRALITY * centrality_score
    )

    return ImageScore(
        path     = img_path,
        score    = round(composite, 4),
        detected = True,
    )


def filter_gesture_folder(
    gesture:  str,
    detector,
    keep:     int,
    dry_run:  bool,
) -> dict:
    folder = os.path.join(IMAGE_ROOT, gesture)

    if not os.path.exists(folder):
        print(f"\n  [SKIP] Not found: {folder}")
        return {}

    all_files = [
        os.path.join(folder, fn)
        for fn in os.listdir(folder)
        if os.path.splitext(fn)[1].lower() in SUPPORTED_EXT
    ]

    total = len(all_files)
    if total == 0:
        print(f"\n  [SKIP] No images in: {folder}")
        return {}

    print(f"\n  '{gesture}': scoring {total:,} images…")
    t0      = time.time()
    scores  = []
    no_hand = 0

    random.shuffle(all_files)  # shuffle for diversity

    for i, fpath in enumerate(all_files):
        result = score_image(fpath, detector)
        scores.append(result)
        if not result.detected:
            no_hand += 1

        if (i + 1) % 1000 == 0:
            elapsed = time.time() - t0
            rate    = (i + 1) / max(elapsed, 0.001)
            eta     = (total - i - 1) / max(rate, 0.001)
            print(f"    {i+1:6,}/{total:,}  "
                  f"rate={rate:.0f}/s  "
                  f"ETA={eta:.0f}s  "
                  f"no_hand={no_hand:,}")

    # Sort best first
    scores.sort(key=lambda x: x.score, reverse=True)

    keep_list  = [s for s in scores if s.detected][:keep]
    keep_paths = {s.path for s in keep_list}
    del_list   = [s for s in scores if s.path not in keep_paths]

    deleted   = 0
    del_bytes = 0
    errors    = 0

    if not dry_run:
        for s in del_list:
            try:
                del_bytes += os.path.getsize(s.path)
                os.remove(s.path)
                deleted += 1
            except OSError:
                errors += 1
    else:
        for s in del_list:
            try:
                del_bytes += os.path.getsize(s.path)
                deleted   += 1
            except OSError:
                pass

    elapsed = time.time() - t0
    kept    = len(keep_list)

    kept_scores = [s.score for s in keep_list]
    avg_score   = float(np.mean(kept_scores)) if kept_scores else 0.0
    min_score   = float(np.min(kept_scores))  if kept_scores else 0.0

    print(f"    Done {elapsed:.0f}s │ "
          f"kept={kept:,} │ "
          f"deleted={deleted:,} │ "
          f"freed={del_bytes/1e6:.1f}MB │ "
          f"avg_score={avg_score:.3f}")

    return {
        "gesture":   gesture,
        "total":     total,
        "kept":      kept,
        "deleted":   deleted,
        "no_hand":   no_hand,
        "errors":    errors,
        "freed_mb":  del_bytes / 1e6,
        "avg_score": avg_score,
        "min_score": min_score,
        "time_s":    elapsed,
    }


def print_report(results: list, dry_run: bool):
    tag = "DRY RUN — nothing deleted" if dry_run else "COMPLETED"
    print(f"\n{'═'*65}")
    print(f"  FILTER REPORT — {tag}")
    print(f"{'═'*65}")

    total_in    = sum(r.get("total",    0) for r in results if r)
    total_kept  = sum(r.get("kept",     0) for r in results if r)
    total_del   = sum(r.get("deleted",  0) for r in results if r)
    total_freed = sum(r.get("freed_mb", 0) for r in results if r)
    total_time  = sum(r.get("time_s",   0) for r in results if r)

    for r in results:
        if not r:
            continue
        pct = r["kept"] / max(r["total"], 1) * 100
        print(f"\n  {r['gesture'].upper()}")
        print(f"    Scanned       : {r['total']:>8,}")
        print(f"    Kept          : {r['kept']:>8,}  ({pct:.1f}%)")
        print(f"    Deleted       : {r['deleted']:>8,}")
        print(f"    No hand found : {r['no_hand']:>8,}")
        print(f"    Avg score     : {r['avg_score']:.4f}")
        print(f"    Min score kept: {r['min_score']:.4f}")
        print(f"    Freed         : {r['freed_mb']:.1f} MB")

    print(f"\n{'─'*65}")
    print(f"  Total scanned : {total_in:>10,}")
    print(f"  Total kept    : {total_kept:>10,}")
    print(f"  Total deleted : {total_del:>10,}")
    print(f"  Disk freed    : {total_freed:>9.1f} MB ({total_freed/1024:.2f} GB)")
    print(f"  Total time    : {total_time:.0f}s ({total_time/60:.1f} min)")

    counts = [r["kept"] for r in results if r and r.get("total", 0) > 0]
    if counts:
        ratio = max(counts) / max(min(counts), 1)
        balance = "GOOD" if ratio <= 1.5 else f"WARNING: {ratio:.1f}x imbalance"
        print(f"  Class balance : {balance}")

    if not dry_run:
        print(f"\n  external_images/ now contains {total_kept:,} clean images.")
        print(f"  Next: python src/extract_from_images.py")
    else:
        print(f"\n  Dry run complete — run without --dry-run to delete.")

    print(f"{'═'*65}")


def main():
    dry_run = "--dry-run" in sys.argv

    print("═" * 65)
    print("  Gesture Car — Permanent Image Quality Filter")
    print(f"  Keep per gesture  : {KEEP_PER_GESTURE:,}")
    print(f"  Target total      : {KEEP_PER_GESTURE * len(GESTURES):,}")
    print(f"  Mode              : {'DRY RUN' if dry_run else 'LIVE — WILL DELETE FILES'}")
    print("═" * 65)

    if not os.path.exists(IMAGE_ROOT):
        print(f"\nERROR: {IMAGE_ROOT} not found")
        return

    # Count all images first
    total_count = 0
    for gesture in GESTURES:
        folder = os.path.join(IMAGE_ROOT, gesture)
        if os.path.exists(folder):
            count = sum(
                1 for fn in os.listdir(folder)
                if os.path.splitext(fn)[1].lower() in SUPPORTED_EXT
            )
            total_count += count
            print(f"  {gesture:12s}: {count:>8,} images")

    print(f"  {'TOTAL':12s}: {total_count:>8,} images")
    print(f"\n  Will KEEP   : {KEEP_PER_GESTURE:,} per gesture")
    print(f"  Will DELETE : ~{max(total_count - KEEP_PER_GESTURE*len(GESTURES),0):,} images")

    if not dry_run:
        print(f"\n  {'!'*55}")
        print(f"  ! PERMANENT DELETE — cannot be undone")
        print(f"  ! Run with --dry-run first to preview")
        print(f"  {'!'*55}")
        confirm = input("\n  Type YES to proceed: ").strip()
        if confirm != "YES":
            print("  Cancelled.")
            return

    detector = mp.solutions.hands.Hands(
        static_image_mode        = True,
        max_num_hands            = 2,
        min_detection_confidence = MIN_DETECT_CONF,
        model_complexity         = 1,
    )

    results = []
    for gesture in GESTURES:
        result = filter_gesture_folder(
            gesture  = gesture,
            detector = detector,
            keep     = KEEP_PER_GESTURE,
            dry_run  = dry_run,
        )
        results.append(result)

    detector.close()
    print_report(results, dry_run)


if __name__ == "__main__":
    main()