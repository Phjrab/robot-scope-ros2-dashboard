"""Explicit local JSON inputs only; archives, links and implicit network access rejected."""

import json
import math
import os
from pathlib import Path
import stat

MAX_FILE = 32 * 1024 * 1024
MAX_LINE = 256 * 1024
MAX_RECORDS = 20000


def reject_constant(_):
    raise ValueError("NONFINITE_JSON")


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def loads(raw):
    value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=pairs)
    return lossless(value)


def lossless(value, depth=0):
    if depth > 32:
        raise ValueError("JSON_DEPTH_LIMIT")
    if isinstance(value, list):
        return [lossless(v, depth + 1) for v in value]
    if isinstance(value, dict):
        out = {}
        for key, v in value.items():
            if key.endswith("_ns") and v is not None:
                if (
                    isinstance(v, bool)
                    or not isinstance(v, (str, int))
                    or not str(v).isdigit()
                    or len(str(v)) > 25
                ):
                    raise ValueError("INVALID_NS")
                v = str(v)
            out[key] = lossless(v, depth + 1)
        return out
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NONFINITE_JSON")
    if isinstance(value, int) and abs(value) > 2**53 - 1:
        raise ValueError("UNSAFE_INTEGER_OUTSIDE_NS")
    return value


def open_local(root, name):
    """Walk beneath an explicitly supplied root using no-follow directory FDs."""
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("LOCAL_RELATIVE_PATH_REQUIRED")
    parts = name.split("/")
    if any(p in ("", ".", "..") for p in parts) or Path(name).suffix not in (
        ".json",
        ".jsonl",
    ):
        raise ValueError("UNSUPPORTED_PATH_OR_ARCHIVE")
    fd = os.open(Path(root).resolve(strict=True), os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        target = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
        )
    finally:
        os.close(fd)
    info = os.fstat(target)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE:
        os.close(target)
        raise ValueError("INPUT_SIZE_OR_TYPE_LIMIT")
    return os.fdopen(target, "rb")


def read_json(root, name, limit=MAX_LINE):
    with open_local(root, name) as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("JSON_SIZE_LIMIT")
    return loads(raw)


def read_jsonl(root, name):
    total = 0
    with open_local(root, name) as source:
        for index in range(MAX_RECORDS + 1):
            raw = source.readline(MAX_LINE + 1)
            if not raw:
                return
            total += len(raw)
            if index == MAX_RECORDS or len(raw) > MAX_LINE or total > MAX_FILE:
                raise ValueError("JSONL_BOUND_EXCEEDED")
            yield loads(raw)


def write_new(path, value):
    """Never replace inputs or existing output; owner-only even with permissive umask."""
    raw = (
        (
            json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        ).encode()
        if not isinstance(value, str)
        else value.encode()
    )
    if len(raw) > MAX_FILE * 2:
        raise ValueError("OUTPUT_LIMIT")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(raw)
