# ─────────────────────────────────────────────────────────────
# Convert trained sklearn Random Forest → ONNX format.
# ONNX runs in browsers via onnxruntime-web.
# Output goes to docs/ folder (GitHub Pages serve directory).
#
# Run: python src/export_model.py
# ─────────────────────────────────────────────────────────────

import os
import sys
import pickle
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import MODEL_FILE, ENCODER_FILE, DOCS_DIR


def main():
    print("Converting model to ONNX for browser inference…")

    # Install skl2onnx if needed
    try:
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType
        import onnx
    except ImportError:
        print("Installing skl2onnx and onnx…")
        os.system("pip install skl2onnx onnx")
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType

    os.makedirs(DOCS_DIR, exist_ok=True)

    onnx_path   = os.path.join(DOCS_DIR, "model.onnx")
    labels_path = os.path.join(DOCS_DIR, "labels.json")

    # Load trained model
    if not os.path.exists(MODEL_FILE):
        print(f"ERROR: Model not found at {MODEL_FILE}")
        print("Run train_model.py first.")
        return

    with open(MODEL_FILE,   'rb') as f: model   = pickle.load(f)
    with open(ENCODER_FILE, 'rb') as f: encoder = pickle.load(f)

    # Convert to ONNX
    # Input: float32 array shape [batch, 63]

    initial_type = [
        ('float_input', FloatTensorType([None, 63]))
    ]

    options = {
        id(model): {
            "zipmap": False
        }
    }

    onnx_model = convert_sklearn(
        model,
        initial_types=initial_type,
        target_opset=12,
        options=options,
    )

    with open(onnx_path, 'wb') as f:
        f.write(onnx_model.SerializeToString())

    # Save label mapping
    labels_data = {
        "labels":      list(encoder.classes_),
        "id_to_label": {str(i): cls for i, cls in enumerate(encoder.classes_)},
    }
    with open(labels_path, 'w') as f:
        json.dump(labels_data, f, indent=2)

    size_mb = os.path.getsize(onnx_path) / (1024 * 1024)
    print(f"ONNX model → {onnx_path}  ({size_mb:.1f} MB)")
    print(f"Labels     → {labels_path}")
    print(f"Classes    : {list(encoder.classes_)}")
    print("\nNext: git add docs/ && git push")


if __name__ == "__main__":
    main()