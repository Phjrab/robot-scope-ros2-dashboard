#!/usr/bin/env python3
"""Stage and validate the private XT16 correction bundle.

The runtime command has no path overrides: it validates only the fixed
deployment paths used by the repository-owned wireless Hesai profile.  The
``stage`` command operates on a private operator directory and never contacts
the sensor or installs files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO


DRIVER_REVISION = "e7e112f0809f0eed5e3c81c55a1a0376474db234"
SDK_REVISION = "9d5dc4fc4ade5be5f6a6ca00e71dd4050b054168"
ACQUISITION_METHOD = "pinned-sdk-jt16-read-only-ptc-and-label-cross-check-v1"
CORRECTION_BYTES = 64
MAX_MANIFEST_BYTES = 32 * 1024
MAX_SERIAL_CHARS = 128


class CalibrationError(RuntimeError):
    """The private calibration bundle violates its fixed contract."""


@dataclass(frozen=True)
class CalibrationContract:
    manifest_path: Path
    correction_path: Path
    expected_uid: int
    expected_gid: int


DEPLOYED_CONTRACT = CalibrationContract(
    manifest_path=Path("/etc/robot-scope/hesai/xt16-calibration.manifest"),
    correction_path=Path("/etc/robot-scope/hesai/xt16-correction.dat"),
    expected_uid=0,
    expected_gid=os.getegid(),
)


def _open_private_regular(
    path: Path,
    *,
    expected_uid: int,
    expected_gid: int,
    require_group_read: bool = True,
) -> tuple[BinaryIO, os.stat_result]:
    try:
        before = path.lstat()
    except OSError as exc:
        raise CalibrationError("required calibration artifact is unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise CalibrationError("calibration artifacts must be regular files")
    if before.st_uid != expected_uid or before.st_gid != expected_gid:
        raise CalibrationError("calibration artifact ownership is invalid")
    mode = stat.S_IMODE(before.st_mode)
    if mode & 0o027:
        raise CalibrationError("calibration artifacts must not be group-writable or accessible by others")
    if not mode & 0o400 or (require_group_read and not mode & 0o040):
        raise CalibrationError(
            "calibration artifacts are not readable by the required principals"
        )

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CalibrationError("calibration artifact could not be opened safely") from exc
    handle = os.fdopen(descriptor, "rb")
    after = os.fstat(handle.fileno())
    if not stat.S_ISREG(after.st_mode) or (before.st_dev, before.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        handle.close()
        raise CalibrationError("calibration artifact changed during validation")
    return handle, after


def _sha256(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    while chunk := handle.read(64 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _require_exact_keys(value: dict[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise CalibrationError(f"{label} fields do not match the fixed schema")


def _read_manifest(contract: CalibrationContract) -> dict[str, Any]:
    handle, metadata = _open_private_regular(
        contract.manifest_path,
        expected_uid=contract.expected_uid,
        expected_gid=contract.expected_gid,
    )
    with handle:
        if metadata.st_size <= 0 or metadata.st_size > MAX_MANIFEST_BYTES:
            raise CalibrationError("calibration manifest size is invalid")
        try:
            document = json.load(handle)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CalibrationError("calibration manifest is not valid JSON") from exc
    if not isinstance(document, dict):
        raise CalibrationError("calibration manifest root must be an object")
    return document


def validate_bundle(contract: CalibrationContract = DEPLOYED_CONTRACT) -> None:
    manifest = _read_manifest(contract)
    _require_exact_keys(
        manifest,
        {
            "schema_version",
            "sensor",
            "driver_revision",
            "sdk_revision",
            "acquisition",
            "correction",
        },
        "manifest",
    )
    if manifest["schema_version"] != 1:
        raise CalibrationError("unsupported calibration manifest schema")
    if manifest["driver_revision"] != DRIVER_REVISION:
        raise CalibrationError("calibration driver revision mismatch")
    if manifest["sdk_revision"] != SDK_REVISION:
        raise CalibrationError("calibration SDK revision mismatch")

    sensor = manifest["sensor"]
    if not isinstance(sensor, dict):
        raise CalibrationError("sensor identity must be an object")
    _require_exact_keys(sensor, {"model", "parser_identity", "serial"}, "sensor")
    if sensor["model"] != "XT16" or sensor["parser_identity"] != "JT16":
        raise CalibrationError("calibration sensor identity mismatch")
    serial = sensor["serial"]
    if (
        not isinstance(serial, str)
        or not serial.strip()
        or serial != serial.strip()
        or len(serial) > MAX_SERIAL_CHARS
        or not serial.isprintable()
    ):
        raise CalibrationError("calibration sensor serial is invalid")

    acquisition = manifest["acquisition"]
    if not isinstance(acquisition, dict):
        raise CalibrationError("acquisition metadata must be an object")
    _require_exact_keys(acquisition, {"method", "timestamp_utc"}, "acquisition")
    if acquisition["method"] != ACQUISITION_METHOD:
        raise CalibrationError("calibration acquisition method mismatch")
    timestamp = acquisition["timestamp_utc"]
    if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
        raise CalibrationError("calibration acquisition timestamp is invalid")
    try:
        datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as exc:
        raise CalibrationError("calibration acquisition timestamp is invalid") from exc

    correction = manifest["correction"]
    if not isinstance(correction, dict):
        raise CalibrationError("correction metadata must be an object")
    _require_exact_keys(correction, {"path", "sha256", "bytes"}, "correction")
    if correction["path"] != str(contract.correction_path):
        raise CalibrationError("calibration correction path mismatch")
    if correction["bytes"] != CORRECTION_BYTES:
        raise CalibrationError("calibration correction length mismatch")
    expected_hash = correction["sha256"]
    if (
        not isinstance(expected_hash, str)
        or len(expected_hash) != 64
        or any(character not in "0123456789abcdef" for character in expected_hash)
    ):
        raise CalibrationError("calibration correction hash is invalid")

    handle, metadata = _open_private_regular(
        contract.correction_path,
        expected_uid=contract.expected_uid,
        expected_gid=contract.expected_gid,
    )
    with handle:
        if metadata.st_size != CORRECTION_BYTES:
            raise CalibrationError("calibration correction length mismatch")
        actual_hash = _sha256(handle)
    if actual_hash != expected_hash:
        raise CalibrationError("calibration correction hash mismatch")


def _read_staged_file(path: Path, *, exact_bytes: int | None = None) -> bytes:
    handle, metadata = _open_private_regular(
        path,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        require_group_read=False,
    )
    with handle:
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise CalibrationError("staged calibration artifacts must be mode 0600")
        if exact_bytes is not None and metadata.st_size != exact_bytes:
            raise CalibrationError("staged calibration artifact length is invalid")
        if metadata.st_size <= 0 or metadata.st_size > MAX_MANIFEST_BYTES:
            raise CalibrationError("staged calibration artifact size is invalid")
        return handle.read()


def stage_manifest(directory: Path, timestamp_utc: str) -> Path:
    if not directory.is_absolute():
        raise CalibrationError("staging directory must be absolute")
    directory_metadata = directory.lstat()
    if not stat.S_ISDIR(directory_metadata.st_mode) or stat.S_ISLNK(
        directory_metadata.st_mode
    ):
        raise CalibrationError("staging directory must be a real directory")
    if directory_metadata.st_uid != os.getuid() or stat.S_IMODE(
        directory_metadata.st_mode
    ) != 0o700:
        raise CalibrationError("staging directory must be owned by the operator and mode 0700")

    correction = _read_staged_file(
        directory / "xt16-correction.dat", exact_bytes=CORRECTION_BYTES
    )
    serial_bytes = _read_staged_file(directory / "xt16-serial.txt")
    try:
        serial = serial_bytes.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise CalibrationError("staged sensor serial is invalid") from exc
    if not serial or len(serial) > MAX_SERIAL_CHARS or not serial.isprintable():
        raise CalibrationError("staged sensor serial is invalid")
    if not isinstance(timestamp_utc, str) or not timestamp_utc.endswith("Z"):
        raise CalibrationError("staging timestamp must be ISO-8601 UTC ending in Z")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp_utc[:-1] + "+00:00")
    except ValueError as exc:
        raise CalibrationError("staging timestamp must be ISO-8601 UTC ending in Z") from exc
    utc_offset = parsed_timestamp.utcoffset()
    if utc_offset is None or utc_offset.total_seconds() != 0:
        raise CalibrationError("staging timestamp must be ISO-8601 UTC ending in Z")

    manifest = {
        "schema_version": 1,
        "sensor": {
            "model": "XT16",
            "parser_identity": "JT16",
            "serial": serial,
        },
        "driver_revision": DRIVER_REVISION,
        "sdk_revision": SDK_REVISION,
        "acquisition": {
            "method": ACQUISITION_METHOD,
            "timestamp_utc": timestamp_utc,
        },
        "correction": {
            "path": str(DEPLOYED_CONTRACT.correction_path),
            "sha256": hashlib.sha256(correction).hexdigest(),
            "bytes": len(correction),
        },
    }
    destination = directory / "xt16-calibration.manifest"
    temporary = directory / ".xt16-calibration.manifest.new"
    if destination.exists() or destination.is_symlink():
        raise CalibrationError("refusing to overwrite a staged calibration manifest")
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage or validate the fixed private XT16 correction bundle."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate only the fixed deployed paths")
    stage = subparsers.add_parser("stage", help="create a manifest in a private directory")
    stage.add_argument("directory", type=Path)
    stage.add_argument("--timestamp-utc", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "validate":
            validate_bundle()
            print("XT16 private correction bundle validated")
        else:
            destination = stage_manifest(arguments.directory, arguments.timestamp_utc)
            print(f"staged private manifest: {destination}")
    except (CalibrationError, OSError) as exc:
        print(f"XT16 calibration validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
