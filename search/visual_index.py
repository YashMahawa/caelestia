#!/home/yash/ML/.venv/bin/python
"""Bounded SigLIP2 visual labelling for Caelestia semantic image search."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

HOME = Path.home()
APP = HOME / ".local/share/caelestia-search"
DB = APP / "index.sqlite3"
MODEL = HOME / "ML/models/siglip2-base-int8-onnx"
CACHE = HOME / ".cache/caelestia-search/siglip-visual"
LABEL_CACHE = APP / "siglip-labels.npz"

LABELS = [
    "identity card", "Aadhaar card", "PAN card", "passport", "driving licence",
    "receipt", "invoice", "bill", "bank statement", "certificate", "form", "letter",
    "handwritten notes", "textbook page", "scanned document", "presentation slide",
    "diagram", "flowchart", "chart", "table", "map", "calendar", "QR code", "barcode",
    "computer screenshot", "mobile app screenshot", "source code", "terminal window",
    "website", "social media post", "chat conversation", "email", "meme", "poster",
    "anime scene", "manga page", "cartoon", "digital illustration", "painting", "sketch",
    "portrait", "selfie", "group photo", "family photo", "baby", "child", "man", "woman",
    "face", "crowd", "wedding", "birthday", "graduation", "sports event", "concert",
    "cat", "dog", "bird", "cow", "horse", "wild animal", "insect", "flower", "tree",
    "mountain", "beach", "river", "lake", "waterfall", "forest", "desert", "sky", "sunset",
    "city", "street", "building", "house", "room", "bedroom", "kitchen", "office",
    "classroom", "laboratory", "library", "hospital", "restaurant", "shop", "temple",
    "car", "motorcycle", "bicycle", "bus", "train", "airplane", "boat", "road sign",
    "laptop", "desktop computer", "phone", "tablet", "television", "headphones", "camera",
    "book", "notebook", "pen", "backpack", "clothing", "shoe", "watch", "jewellery",
    "food", "Indian food", "pizza", "burger", "momos", "dessert", "fruit", "drink",
    "medical image", "X-ray", "MRI scan", "medicine", "prescription", "fitness workout",
    "physics problem", "chemistry equation", "mathematics equation", "engineering drawing",
    "product photo", "package", "logo", "icon", "wallpaper", "blurry photo", "dark photo",
]


def allowed() -> bool:
    try:
        ultra = json.loads((HOME / ".local/state/caelestia/ultra-power.json").read_text())
        if ultra.get("active"):
            return False
    except (OSError, ValueError):
        pass
    try:
        status = subprocess.run(["waydroid", "status"], capture_output=True, text=True, timeout=3).stdout
        if "Container:\tRUNNING" in status:
            return False
    except (OSError, subprocess.TimeoutExpired):
        pass
    return True


def normalise(values: np.ndarray) -> np.ndarray:
    values = values.astype(np.float32)
    return values / np.maximum(np.linalg.norm(values, axis=-1, keepdims=True), 1e-9)


def label_vectors(core) -> np.ndarray:
    if LABEL_CACHE.exists():
        saved = np.load(LABEL_CACHE)
        if list(saved["labels"]) == LABELS:
            return saved["vectors"]
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(MODEL / "tokenizer.json"))
    tokenizer.enable_truncation(max_length=64)
    tokenizer.enable_padding(length=64, pad_id=0, pad_token="<pad>", direction="right")
    model = core.read_model(MODEL / "onnx/text_model_int8.onnx")
    batch_size = 16
    model.reshape({"input_ids": [batch_size, 64]})
    compiled = core.compile_model(model, "CPU", {"PERFORMANCE_HINT": "THROUGHPUT", "CACHE_DIR": str(CACHE / "text")})
    output = compiled.output("pooler_output")
    vectors = []
    prompts = [f"a photo of {label}" for label in LABELS]
    for offset in range(0, len(prompts), batch_size):
        batch = prompts[offset:offset + batch_size]
        actual = len(batch)
        batch.extend([batch[-1]] * (batch_size - actual))
        encoded = tokenizer.encode_batch(batch)
        input_ids = np.asarray([item.ids for item in encoded], dtype=np.int64)
        vectors.append(compiled({"input_ids": input_ids})[output][:actual])
    result = normalise(np.vstack(vectors))
    np.savez_compressed(LABEL_CACHE, labels=np.array(LABELS), vectors=result)
    return result


def image_tensor(path: Path) -> np.ndarray:
    with Image.open(path) as source:
        image = ImageOps.fit(source.convert("RGB"), (224, 224), method=Image.Resampling.BICUBIC)
        values = np.asarray(image, dtype=np.float32) / 255.0
    values = (values - 0.5) / 0.5
    return np.transpose(values, (2, 0, 1))[None, ...]


def main(limit: int = 16) -> None:
    if not allowed():
        print(json.dumps({"processed": 0, "reason": "ultra-power-or-waydroid"}))
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA busy_timeout=60000")
    db.execute("CREATE TABLE IF NOT EXISTS visual_tags(path TEXT PRIMARY KEY,mtime_ns INTEGER NOT NULL,tags TEXT NOT NULL)")
    rows = db.execute(
        """SELECT f.path,f.mtime_ns FROM files f LEFT JOIN visual_tags v ON v.path=f.path
           WHERE f.mime LIKE 'image/%' AND (v.path IS NULL OR v.mtime_ns != f.mtime_ns)
           ORDER BY f.mtime_ns DESC LIMIT ?""", (limit,)
    ).fetchall()
    if not rows:
        print(json.dumps({"processed": 0, "remaining": 0}))
        return

    import openvino as ov
    core = ov.Core()
    labels = label_vectors(core)
    model = core.read_model(MODEL / "onnx/vision_model_fp16.onnx")
    model.reshape({"pixel_values": [1, 3, 224, 224]})
    compiled = core.compile_model(model, "GPU", {"PERFORMANCE_HINT": "LATENCY", "CACHE_DIR": str(CACHE / "vision")})
    output = compiled.output("pooler_output")

    processed = 0
    for raw, mtime_ns in rows:
        if not allowed():
            break
        path = Path(raw)
        try:
            vector = normalise(compiled({"pixel_values": image_tensor(path)})[output])[0]
            similarity = labels @ vector
            best = np.argsort(similarity)[::-1][:8]
            tags = [LABELS[index] for index in best if similarity[index] >= 0.05]
            if not tags:
                tags = [LABELS[int(best[0])]]
            tag_text = ", ".join(tags)
            db.execute(
                "INSERT INTO visual_tags(path,mtime_ns,tags) VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET mtime_ns=excluded.mtime_ns,tags=excluded.tags",
                (raw, mtime_ns, tag_text),
            )
            db.execute(
                "INSERT INTO pending(path,queued_at) VALUES(?,?) ON CONFLICT(path) DO UPDATE SET queued_at=excluded.queued_at",
                (raw, time.time_ns()),
            )
            db.commit()
            processed += 1
        except Exception as error:
            print(f"visual_index: {path}: {error}", file=sys.stderr)
            # Do not retry the same corrupt/unsupported image every 30 minutes.
            # A real replacement changes mtime and becomes eligible again.
            db.execute(
                "INSERT INTO visual_tags(path,mtime_ns,tags) VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET mtime_ns=excluded.mtime_ns,tags=excluded.tags",
                (raw, mtime_ns, "unreadable image"),
            )
            db.commit()
    remaining = db.execute(
        """SELECT count(*) FROM files f LEFT JOIN visual_tags v ON v.path=f.path
           WHERE f.mime LIKE 'image/%' AND (v.path IS NULL OR v.mtime_ns != f.mtime_ns)"""
    ).fetchone()[0]
    print(json.dumps({"processed": processed, "remaining": remaining}))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 16)
