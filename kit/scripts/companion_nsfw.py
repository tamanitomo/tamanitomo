"""CPU-only NSFW classification. No network access or automatic model downloads."""

from __future__ import annotations
import argparse
import json
from pathlib import Path

MODEL_ID = "NudeNet/320n"
REVISION = "nudenet-3.4.2"
SENSITIVE = {
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "ANUS_EXPOSED",
    "BUTTOCKS_EXPOSED",
}


def classify(path, model_dir=None):
    import numpy as np
    import onnxruntime as ort
    import nudenet
    from nudenet import NudeDetector
    from PIL import Image, ImageOps

    # Construct explicitly: upstream's constructor does not honor its providers argument.
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    detector = NudeDetector.__new__(NudeDetector)
    detector.onnx_session = ort.InferenceSession(
        str(Path(nudenet.__file__).parent / "320n.onnx"),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    detector.input_width = detector.input_height = 320
    detector.input_name = detector.onnx_session.get_inputs()[0].name
    with Image.open(path) as image:
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("Animated images require review of every frame")
        # NudeNet takes OpenCV's BGR pixels; apply orientation before inference.
        pixels = np.asarray(ImageOps.exif_transpose(image).convert("RGB"))[
            :, :, ::-1
        ].copy()
    detections = detector.detect(pixels)
    scores = [float(d["score"]) for d in detections if d["class"] in SENSITIVE]
    score = max(scores, default=0.0)
    if not np.isfinite(score):
        raise ValueError("Invalid detector output")
    rating = "nsfw" if score >= 0.5 else "unknown" if score >= 0.2 else "safe"
    return {
        "rating": rating,
        "detections": detections,
        "sensitive_score": score,
        "provider": "local-nsfw",
        "model": MODEL_ID,
        "revision": REVISION,
        "scope": "nudity_only",
        "reason": "Local exposed-anatomy detector; scene match and clothed sexual activity were not checked.",
    }


def scan(c, path):
    import os
    import subprocess
    from companion_platform import file_lock

    root = c.hermes_root / "companion-engines" / "nsfw"
    python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        raise ValueError("Install the local NSFW scanner on this host first")
    # Serialize across profiles so simultaneous captures cannot multiply model memory.
    with file_lock(root / ".scan.lock"):
        result = subprocess.run(
            [str(python), str(Path(__file__).resolve()), str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    if result.returncode:
        raise ValueError("Local NSFW scanner failed; image remains unreviewed")
    data = json.loads(result.stdout)
    if data.get("rating") not in ("safe", "nsfw", "unknown"):
        raise ValueError("Invalid local scan decision")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    print(json.dumps(classify(args.image)))
