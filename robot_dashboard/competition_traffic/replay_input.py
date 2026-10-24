"""Bounded local-file providers. VideoCapture is restricted to an existing file."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import uuid

import cv2
import numpy as np

from .config import finite, sha256_file
from .frames import Frame

IMAGES = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEOS = {".avi", ".mp4", ".mkv", ".mov"}


@dataclass
class InputItem:
    path: Path
    sha256: str
    size_bytes: int
    metadata: dict

    def manifest(self):
        return {"path": str(self.path), "sha256": self.sha256,
                "size_bytes": self.size_bytes, "metadata": self.metadata}


def inspect_inputs(path, *, max_frames=10000):
    if type(max_frames) is not int or not 1 <= max_frames <= 10000:
        raise ValueError("MAX_FRAMES_INVALID")
    root = Path(path).resolve(strict=True)
    if root.is_file() and root.suffix.lower() == ".jsonl":
        result = []
        with root.open(encoding="utf-8") as stream:
            for line in stream:
                if len(result) >= max_frames:
                    break
                record = json.loads(line)
                image = (root.parent / record["image"]).resolve(strict=True)
                if root.parent not in image.parents or image.suffix.lower() not in IMAGES:
                    raise ValueError("MANIFEST_IMAGE_OUTSIDE_ROOT")
                if not finite(record["replay_time_s"], 0, 1e9):
                    raise ValueError("REPLAY_TIME_INVALID")
                digest = sha256_file(image)
                if digest != record["sha256"]:
                    raise ValueError("CAPTURE_CHECKSUM_MISMATCH")
                result.append(InputItem(image, digest, image.stat().st_size,
                                        {"origin": "explicit_replay_manifest", **record}))
        if not result:
            raise ValueError("INPUT_IMAGES_REQUIRED")
        return result
    files = []
    dataset = root.is_dir() and (root / "samples").is_dir() and (root / "manifest.json").is_file()
    if root.is_file():
        if root.suffix.lower() not in IMAGES | VIDEOS:
            raise ValueError("INPUT_EXTENSION_UNSUPPORTED")
        files = [root]
    elif dataset:
        files = sorted((root / "samples").glob("[0-9]*/go2_front.jpg"))
    elif root.is_dir():
        files = sorted(p for p in root.iterdir() if p.suffix.lower() in IMAGES and p.is_file())
    if not files:
        raise ValueError("INPUT_IMAGES_REQUIRED")
    selected = files[:max_frames]
    result = []
    for file in selected:
        resolved = file.resolve(strict=True)
        if root.is_dir() and root not in resolved.parents:
            raise ValueError("INPUT_SYMLINK_ESCAPE")
        info = {"origin": "user_supplied_local_file", "dataset_sample": file.parent.name if dataset else None}
        metadata_path = file.parent / "metadata.json"
        if dataset and metadata_path.is_file():
            if root not in metadata_path.resolve().parents:
                raise ValueError("METADATA_SYMLINK_ESCAPE")
            raw = metadata_path.read_bytes()
            if len(raw) > 1024 * 1024:
                raise ValueError("METADATA_TOO_LARGE")
            info["capture"] = json.loads(raw)
            info["metadata_sha256"] = hashlib.sha256(raw).hexdigest()
        digest = sha256_file(resolved)
        if dataset:
            expected = info.get("capture", {}).get("sources", {}).get("go2_front", {}).get("sha256")
            info["capture_checksum_matches"] = None if expected is None else digest == expected
            if expected is not None and digest != expected:
                raise ValueError("CAPTURE_CHECKSUM_MISMATCH")
        result.append(InputItem(resolved, digest, resolved.stat().st_size, info))
    return result


def iter_frames(items, *, fps, binding_id, max_frames=10000):
    if not finite(fps, .01, 240):
        raise ValueError("EXPLICIT_REPLAY_FPS_REQUIRED")
    epoch = "replay-" + uuid.uuid4().hex
    sequence = 0
    for item in items:
        if item.path.suffix.lower() in VIDEOS:
            capture = cv2.VideoCapture(str(item.path))
            if not capture.isOpened():
                capture.release()
                raise ValueError("VIDEO_DECODE_FAILED")
            expected_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            video_index = 0
            try:
                while sequence < max_frames:
                    ok, bgr = capture.read()
                    if not ok:
                        if video_index == 0 or (expected_count > 0 and video_index < expected_count):
                            raise ValueError("VIDEO_TRUNCATED_OR_CORRUPT")
                        break
                    yield _frame(item, bgr, sequence, epoch, fps, binding_id, video_index)
                    sequence += 1
                    video_index += 1
            finally:
                capture.release()
        else:
            if item.size_bytes > 32 * 1024 * 1024:
                raise ValueError("IMAGE_TOO_LARGE")
            data = item.path.read_bytes()
            if hashlib.sha256(data).hexdigest() != item.sha256:
                raise ValueError("INPUT_CHANGED_AFTER_MANIFEST")
            bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            yield _frame(item, bgr, sequence, epoch, fps, binding_id, None)
            sequence += 1
        if sequence >= max_frames:
            break


def _frame(item, bgr, sequence, epoch, fps, binding_id, video_index):
    t = item.metadata.get("replay_time_s", sequence / fps)
    # A local replay schedule is NOT the historical camera's source timestamp.
    # Preserve original metadata without subtracting its remote monotonic clock.
    handle = item.sha256 if video_index is None else hashlib.sha256(
        f"{item.sha256}:{video_index}".encode()).hexdigest()
    return Frame(bgr, "offline-rgb", epoch, sequence, str(round(t * 1e9)),
                 "fixture", 0., t, True, "RECORDED_RGB_OFFLINE_VIRTUAL_CLOCK", handle,
                 binding_id, identity_verified=True, original_metadata={"input_sha256": item.sha256,
                 "video_frame_index": video_index, "explicit_replay_fps": fps, **item.metadata})
