"""Fail-closed competition release manifest and offline package support.

This module only reads an already verified checkout and model registry.  It
does not install packages, change services, activate models, or alter robot
configuration.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Mapping

from robot_dashboard.competition import CompetitionStateManager
from robot_dashboard.model_registry import MODEL_TASKS, PACKAGE_FILES, ModelRegistry


RELEASE_SCHEMA = "robot-scope.competition-release/v1"
CHECKSUM_SCHEMA = "robot-scope.offline-package-checksums/v1"
RELEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
SCHEMA_NAME_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 4096
MAX_TEXT_SCAN_BYTES = 2 * 1024 * 1024
REQUIRED_REPOSITORY_FILES = (
    "package-lock.json",
    "requirements.txt",
    "requirements-quality.txt",
    "pyproject.toml",
    "scripts/robot_scope_doctor.py",
    "scripts/robot_scope_acceptance.py",
    "docs/WP08_RELEASE_LOCK_ROLLBACK_RUNBOOK.md",
    "deploy/robot-scope.service.example",
)
MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "release_id",
        "git_commit",
        "dashboard_version",
        "robot_side_agent_version",
        "schema_versions",
        "active_model_ids",
        "active_model_sha256",
        "previous_model_ids",
        "previous_model_sha256",
        "jetpack_tensorrt_identity",
        "camera_profile",
        "network_config_fingerprint",
        "ros",
        "map_revision",
        "mission_revision",
        "acceptance_report_ids",
        "created_at",
    }
)
SECRET_RULES = (
    re.compile(rb"-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----"),
    re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
    re.compile(rb"\bglpat-[A-Za-z0-9_-]{20,255}\b"),
    re.compile(rb"\bROBOT_SCOPE_CONTROL_BRIDGE_KEY\s*=\s*['\"]?[0-9a-fA-F]{64,}"),
)
PRIVATE_INPUT_SECRET_RE = re.compile(
    r"(?i)(?:password|secret|token|api[_-]?key|bridge[_-]?key)\s*[:=]\s*\S+"
)
URL_USERINFO_RE = re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)
ACCEPTANCE_STATUSES = ("PASS", "FAIL", "BLOCKED", "NOT_RUN")


class ReleasePackageError(RuntimeError):
    """Release input or immutable package validation failed."""


def _safe_text(value: object, label: str, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise ReleasePackageError(f"{label} is invalid")
    clean = " ".join(value.split())
    if (
        not clean
        or len(clean) > maximum
        or any(ord(character) < 32 for character in clean)
        or not SAFE_ID_RE.fullmatch(clean)
    ):
        raise ReleasePackageError(f"{label} is invalid")
    return clean


def _utc(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64 or not value.endswith("Z"):
        raise ReleasePackageError("created_at is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ReleasePackageError("created_at is invalid") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ReleasePackageError("created_at is invalid")
    return value


def _string_map(value: object, label: str, *, allow_empty: bool = False) -> Dict[str, str]:
    if not isinstance(value, dict) or len(value) > 64 or (not value and not allow_empty):
        raise ReleasePackageError(f"{label} is invalid")
    result: Dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not SCHEMA_NAME_RE.fullmatch(key):
            raise ReleasePackageError(f"{label} is invalid")
        result[key] = _safe_text(item, f"{label}.{key}")
    return result


def _model_ids(value: object, label: str, *, allow_empty: bool) -> Dict[str, str]:
    result = _string_map(value, label, allow_empty=allow_empty)
    if set(result) - MODEL_TASKS:
        raise ReleasePackageError(f"{label} contains an unsupported task")
    return result


def _model_hashes(
    value: object,
    label: str,
    expected_tasks: Iterable[str],
) -> Dict[str, Dict[str, str]]:
    if not isinstance(value, dict) or set(value) != set(expected_tasks):
        raise ReleasePackageError(f"{label} does not match model ids")
    result: Dict[str, Dict[str, str]] = {}
    for task, hashes in value.items():
        if not isinstance(hashes, dict) or set(hashes) != {"package_sha256", "engine_sha256"}:
            raise ReleasePackageError(f"{label}.{task} is invalid")
        if any(not isinstance(item, str) or not HASH_RE.fullmatch(item) for item in hashes.values()):
            raise ReleasePackageError(f"{label}.{task} is invalid")
        result[task] = dict(hashes)
    return result


def validate_release_manifest(value: object) -> Dict[str, Any]:
    """Return a detached validated release manifest with an exact schema."""

    if not isinstance(value, dict) or frozenset(value) != MANIFEST_KEYS:
        raise ReleasePackageError("release manifest schema is invalid")
    if value.get("schema_version") != RELEASE_SCHEMA:
        raise ReleasePackageError("release manifest schema version is unsupported")
    release_id = value.get("release_id")
    commit = value.get("git_commit")
    fingerprint = value.get("network_config_fingerprint")
    if not isinstance(release_id, str) or not RELEASE_ID_RE.fullmatch(release_id):
        raise ReleasePackageError("release_id is invalid")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise ReleasePackageError("git_commit is invalid")
    if not isinstance(fingerprint, str) or not HASH_RE.fullmatch(fingerprint):
        raise ReleasePackageError("network_config_fingerprint must be a SHA-256 digest")
    active_ids = _model_ids(value.get("active_model_ids"), "active_model_ids", allow_empty=False)
    previous_ids = _model_ids(value.get("previous_model_ids"), "previous_model_ids", allow_empty=True)
    active_hashes = _model_hashes(value.get("active_model_sha256"), "active_model_sha256", active_ids)
    previous_hashes = _model_hashes(
        value.get("previous_model_sha256"), "previous_model_sha256", previous_ids
    )
    if set(active_ids).intersection(previous_ids) and any(
        active_ids[task] == previous_ids[task] for task in set(active_ids).intersection(previous_ids)
    ):
        raise ReleasePackageError("active and previous model ids must differ")
    identity = value.get("jetpack_tensorrt_identity")
    if not isinstance(identity, dict) or set(identity) != {
        "platform", "jetpack_version", "tensorrt_version", "gpu_identity"
    }:
        raise ReleasePackageError("JetPack/TensorRT identity is invalid")
    identity_clean = {key: _safe_text(identity[key], f"target.{key}") for key in identity}
    camera = _string_map(value.get("camera_profile"), "camera_profile")
    ros = value.get("ros")
    if not isinstance(ros, dict) or set(ros) != {"distro", "rmw", "domain_id"}:
        raise ReleasePackageError("ROS identity is invalid")
    domain_id = ros.get("domain_id")
    if isinstance(domain_id, bool) or not isinstance(domain_id, int) or not 0 <= domain_id <= 232:
        raise ReleasePackageError("ROS domain_id is invalid")
    ros_clean = {
        "distro": _safe_text(ros.get("distro"), "ros.distro"),
        "rmw": _safe_text(ros.get("rmw"), "ros.rmw"),
        "domain_id": domain_id,
    }
    revisions: Dict[str, str | None] = {}
    for key in ("map_revision", "mission_revision"):
        raw = value.get(key)
        revisions[key] = None if raw is None else _safe_text(raw, key)
    reports = value.get("acceptance_report_ids")
    if (
        not isinstance(reports, list)
        or not 1 <= len(reports) <= 64
        or len(set(reports)) != len(reports)
    ):
        raise ReleasePackageError("acceptance_report_ids is invalid")
    report_ids = []
    for item in reports:
        if not isinstance(item, str) or not RELEASE_ID_RE.fullmatch(item):
            raise ReleasePackageError("acceptance report id is invalid")
        report_ids.append(item)
    return {
        "schema_version": RELEASE_SCHEMA,
        "release_id": release_id,
        "git_commit": commit,
        "dashboard_version": _safe_text(value.get("dashboard_version"), "dashboard_version"),
        "robot_side_agent_version": _safe_text(
            value.get("robot_side_agent_version"), "robot_side_agent_version"
        ),
        "schema_versions": _string_map(value.get("schema_versions"), "schema_versions"),
        "active_model_ids": active_ids,
        "active_model_sha256": active_hashes,
        "previous_model_ids": previous_ids,
        "previous_model_sha256": previous_hashes,
        "jetpack_tensorrt_identity": identity_clean,
        "camera_profile": camera,
        "network_config_fingerprint": fingerprint,
        "ros": ros_clean,
        **revisions,
        "acceptance_report_ids": report_ids,
        "created_at": _utc(value.get("created_at")),
    }


def load_release_manifest(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ReleasePackageError("release manifest must be a regular file")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_MANIFEST_BYTES:
        raise ReleasePackageError("release manifest size is invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleasePackageError("release manifest is unreadable") from exc
    return validate_release_manifest(value)


def _hash_file(path: Path, maximum: int = MAX_ARCHIVE_BYTES) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise ReleasePackageError("release artifact is not a regular file")
    size = path.stat().st_size
    if size <= 0 or size > maximum:
        raise ReleasePackageError("release artifact size is invalid")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), size


def _safe_archive_name(name: str) -> str:
    pure = PurePosixPath(name)
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or any(part in {"", ".", ".."} for part in pure.parts)
        or len(name) > 240
    ):
        raise ReleasePackageError("offline package contains an unsafe path")
    return pure.as_posix()


def _scan_bytes(payload: bytes, name: str) -> None:
    if any(rule.search(payload) for rule in SECRET_RULES):
        raise ReleasePackageError(f"secret-like content rejected in {name}")


def _validate_private_text(path: Path, label: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReleasePackageError(f"{label} is unreadable") from exc
    if PRIVATE_INPUT_SECRET_RE.search(text) or URL_USERINFO_RE.search(text):
        raise ReleasePackageError(f"credential-like content rejected in {label}")
    return text


def _validate_acceptance_report(
    report: object,
    commit: str,
) -> tuple[set[str], set[str]]:
    if not isinstance(report, dict):
        raise ReleasePackageError("acceptance report is invalid")
    summary = report.get("summary")
    checks = report.get("checks")
    if (
        report.get("schema") != "robot-scope.hardware-acceptance"
        or report.get("schema_version") != 1
        or report.get("commit") != commit
        or not isinstance(summary, dict)
        or set(summary) != set(ACCEPTANCE_STATUSES)
        or not isinstance(checks, list)
        or len(checks) > 512
    ):
        raise ReleasePackageError("acceptance evidence does not match the release")
    counts = {status: 0 for status in ACCEPTANCE_STATUSES}
    supervised_observed: set[str] = set()
    supervised_passed: set[str] = set()
    for check in checks:
        if not isinstance(check, dict):
            raise ReleasePackageError("acceptance report checks are invalid")
        check_id = check.get("id")
        status_value = check.get("status")
        if (
            not isinstance(check_id, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,95}", check_id)
            or status_value not in ACCEPTANCE_STATUSES
        ):
            raise ReleasePackageError("acceptance report checks are invalid")
        counts[status_value] += 1
        if check_id.startswith("supervised."):
            supervised_observed.add(check_id)
            if status_value == "PASS" and check.get("manual_action") is True:
                supervised_passed.add(check_id)
    if counts != summary or counts["FAIL"] or counts["BLOCKED"]:
        raise ReleasePackageError(
            "acceptance evidence must match the release commit with no FAIL/BLOCKED"
        )
    return supervised_observed, supervised_passed


class OfflineReleaseBuilder:
    """Build one immutable package from fixed, validated local inputs."""

    def __init__(self, project_root: Path) -> None:
        requested = Path(project_root).expanduser()
        if not requested.is_absolute() or requested.is_symlink() or not requested.is_dir():
            raise ReleasePackageError("project root is invalid")
        self.project_root = requested.resolve(strict=True)
        if self.project_root == Path("/") or not (self.project_root / ".git").exists():
            raise ReleasePackageError("project root is not a repository checkout")
        self.runtime_root = self.project_root / "runtime"
        self.release_root = self.runtime_root / "releases"
        self.competition_root = self.runtime_root / "competition"
        self.registry_root = self.runtime_root / "model-registry"
        self.release_input_root = self.runtime_root / "release-input"

    def _git(self, *arguments: str, maximum: int = MAX_MANIFEST_BYTES) -> bytes:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.project_root), *arguments],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ReleasePackageError("repository identity could not be verified") from exc
        if len(result.stdout) > maximum:
            raise ReleasePackageError("repository command output exceeds its limit")
        return result.stdout

    def _verify_checkout(self, manifest: Mapping[str, Any]) -> None:
        head = self._git("rev-parse", "HEAD").decode("ascii").strip()
        if head != manifest["git_commit"]:
            raise ReleasePackageError("release manifest does not match checkout HEAD")
        if self._git("status", "--porcelain", "--untracked-files=no").strip():
            raise ReleasePackageError("tracked checkout must be clean before packaging")
        tracked = set(
            item.decode("utf-8", "surrogateescape")
            for item in self._git("ls-files", "-z", maximum=16 * 1024 * 1024).split(b"\0")
            if item
        )
        missing = [item for item in REQUIRED_REPOSITORY_FILES if item not in tracked]
        if missing:
            raise ReleasePackageError("release checkout is missing required tracked files")
        python = (
            os.fspath(self.project_root / ".venv" / "bin" / "python")
            if (self.project_root / ".venv" / "bin" / "python").is_file()
            else "python3"
        )
        try:
            scanner = subprocess.run(
                [
                    python,
                    os.fspath(self.project_root / "scripts" / "check_repository_secrets.py"),
                ],
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise ReleasePackageError("tracked-source secret scan could not run") from exc
        if scanner.returncode != 0:
            raise ReleasePackageError("tracked-source secret scan failed")

    def _prepare_release_root(self) -> None:
        current = self.project_root
        for part in ("runtime", "releases"):
            current = current / part
            if current.is_symlink():
                raise ReleasePackageError("release output directory is unsafe")
        self.release_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if (
            self.release_root.is_symlink()
            or self.release_root.resolve(strict=True) != self.release_root
            or self.release_root.stat().st_uid != os.geteuid()
        ):
            raise ReleasePackageError("release output directory is unsafe")
        os.chmod(self.release_root, 0o700)

    def _verify_lock(self) -> None:
        if not (self.competition_root / "state.json").is_file():
            raise ReleasePackageError("Competition Lock state is unavailable")
        try:
            locked = CompetitionStateManager(self.competition_root).snapshot()["locked"]
        except Exception as exc:
            raise ReleasePackageError("Competition Lock state is unavailable") from exc
        if locked is not True:
            raise ReleasePackageError("Competition Lock must be enabled before packaging")

    def _model_files(self, manifest: Mapping[str, Any]) -> list[tuple[str, Path]]:
        try:
            registry = ModelRegistry(self.registry_root)
            snapshot = registry.list_models()
        except Exception as exc:
            raise ReleasePackageError("validated model registry is unavailable") from exc
        records = {record["model_id"]: record for record in snapshot["models"]}
        files: list[tuple[str, Path]] = []
        for state in ("active", "previous"):
            ids = manifest[f"{state}_model_ids"]
            hashes = manifest[f"{state}_model_sha256"]
            registry_ids = snapshot[state]
            if ids != registry_ids:
                raise ReleasePackageError(f"{state} model ids do not match the registry")
            for task, model_id in ids.items():
                record = records.get(model_id)
                expected = hashes[task]
                if (
                    not record
                    or record.get("state") != state
                    or record.get("task") != task
                    or record.get("package_sha256") != expected["package_sha256"]
                    or record.get("supported_target")
                    != manifest["jetpack_tensorrt_identity"]
                    or not isinstance(record.get("engine"), dict)
                    or record["engine"].get("sha256") != expected["engine_sha256"]
                ):
                    raise ReleasePackageError(f"{state} model identity is invalid")
                package = registry.packages / f"{model_id}-{record['package_sha256'][:16]}"
                engine = registry.engines / model_id / record["engine"]["sha256"]
                if registry._package_digest(package) != record["package_sha256"]:
                    raise ReleasePackageError("model package changed after validation")
                engine_sha, _ = _hash_file(engine / "engine.plan")
                if engine_sha != record["engine"]["sha256"]:
                    raise ReleasePackageError("model engine changed after validation")
                prefix = f"models/{state}/{task}/{model_id}"
                for name in sorted(PACKAGE_FILES):
                    files.append((f"{prefix}/package/{name}", package / name))
                for name in ("engine.plan", "engine-validation.json", "build.log"):
                    files.append((f"{prefix}/engine/{name}", engine / name))
        return files

    def _acceptance_files(self, manifest: Mapping[str, Any]) -> list[tuple[str, Path]]:
        files: list[tuple[str, Path]] = []
        supervised_passed: set[str] = set()
        supervised_observed: set[str] = set()
        for report_id in manifest["acceptance_report_ids"]:
            path = self.release_input_root / "acceptance" / f"{report_id}.json"
            _hash_file(path, 16 * 1024 * 1024)
            try:
                report = json.loads(_validate_private_text(path, "acceptance report"))
            except json.JSONDecodeError as exc:
                raise ReleasePackageError("acceptance report is unreadable") from exc
            observed, passed = _validate_acceptance_report(report, manifest["git_commit"])
            supervised_observed.update(observed)
            supervised_passed.update(passed)
            files.append((f"acceptance/{report_id}.json", path))
        if not supervised_observed or supervised_observed - supervised_passed:
            raise ReleasePackageError("required supervised acceptance evidence is incomplete")
        return files

    @staticmethod
    def _zip_file(archive: zipfile.ZipFile, name: str, path: Path) -> tuple[str, int]:
        name = _safe_archive_name(name)
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as source, archive.open(name, "w", force_zip64=True) as destination:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    raise ReleasePackageError("release artifact exceeds its size limit")
                if size <= MAX_TEXT_SCAN_BYTES:
                    _scan_bytes(chunk, name)
                digest.update(chunk)
                destination.write(chunk)
        if size <= 0:
            raise ReleasePackageError("release artifact is empty")
        return digest.hexdigest(), size

    @staticmethod
    def _zip_bytes(archive: zipfile.ZipFile, name: str, payload: bytes) -> tuple[str, int]:
        _safe_archive_name(name)
        _scan_bytes(payload, name)
        archive.writestr(name, payload)
        return hashlib.sha256(payload).hexdigest(), len(payload)

    def build(self, manifest_path: Path) -> Path:
        manifest = load_release_manifest(manifest_path)
        self._verify_checkout(manifest)
        self._verify_lock()
        model_files = self._model_files(manifest)
        acceptance_files = self._acceptance_files(manifest)
        install_manifest = self.release_input_root / "python-install-manifest.txt"
        _hash_file(install_manifest, 16 * 1024 * 1024)
        _validate_private_text(install_manifest, "Python install manifest")
        self._prepare_release_root()
        output = self.release_root / f"{manifest['release_id']}.zip"
        if output.exists() or output.is_symlink():
            raise ReleasePackageError("release id already exists")
        manifest_bytes = json.dumps(
            manifest, allow_nan=False, indent=2, sort_keys=True
        ).encode("utf-8") + b"\n"
        checksums: Dict[str, Dict[str, Any]] = {}
        with tempfile.TemporaryDirectory(dir=self.release_root) as temporary:
            temporary_root = Path(temporary)
            source_archive = temporary_root / "source.tar"
            with source_archive.open("wb") as destination:
                try:
                    subprocess.run(
                        ["git", "-C", str(self.project_root), "archive", "--format=tar", "HEAD"],
                        check=True,
                        stdout=destination,
                        stderr=subprocess.PIPE,
                    )
                except (OSError, subprocess.CalledProcessError) as exc:
                    raise ReleasePackageError("verified source archive could not be created") from exc
            temporary_output = temporary_root / "release.zip"
            with zipfile.ZipFile(temporary_output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                digest, size = self._zip_bytes(archive, "release-manifest.json", manifest_bytes)
                checksums["release-manifest.json"] = {"sha256": digest, "bytes": size}
                fixed_files = [
                    (f"source/robot-scope-{manifest['git_commit']}.tar", source_archive),
                    ("dependencies/python-install-manifest.txt", install_manifest),
                    ("dependencies/requirements.txt", self.project_root / "requirements.txt"),
                    ("dependencies/requirements-quality.txt", self.project_root / "requirements-quality.txt"),
                    ("dependencies/package-lock.json", self.project_root / "package-lock.json"),
                    ("tools/robot_scope_doctor.py", self.project_root / "scripts/robot_scope_doctor.py"),
                    ("tools/robot_scope_acceptance.py", self.project_root / "scripts/robot_scope_acceptance.py"),
                    ("runbooks/WP08_RELEASE_LOCK_ROLLBACK_RUNBOOK.md", self.project_root / "docs/WP08_RELEASE_LOCK_ROLLBACK_RUNBOOK.md"),
                ]
                for path in sorted((self.project_root / "deploy").glob("*.example")):
                    fixed_files.append((f"service-examples/{path.name}", path))
                fixed_files.extend(model_files)
                fixed_files.extend(acceptance_files)
                for name, path in fixed_files:
                    digest, size = self._zip_file(archive, name, path)
                    checksums[name] = {"sha256": digest, "bytes": size}
                checksum_payload = json.dumps(
                    {"schema_version": CHECKSUM_SCHEMA, "files": checksums},
                    allow_nan=False,
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8") + b"\n"
                self._zip_bytes(archive, "checksums.json", checksum_payload)
            verify_offline_package(temporary_output)
            os.chmod(temporary_output, 0o600)
            try:
                os.link(temporary_output, output, follow_symlinks=False)
            except FileExistsError as exc:
                raise ReleasePackageError("release id already exists") from exc
            directory = os.open(self.release_root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        os.chmod(output, 0o600)
        return output


def verify_offline_package(path: Path) -> Dict[str, Any]:
    """Verify package paths, manifest identity, and every declared checksum."""

    _hash_file(Path(path))
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if not 1 < len(entries) <= MAX_ARCHIVE_ENTRIES:
                raise ReleasePackageError("offline package entry count is invalid")
            names = [_safe_archive_name(entry.filename) for entry in entries]
            if len(names) != len(set(names)) or any(entry.is_dir() for entry in entries):
                raise ReleasePackageError("offline package layout is invalid")
            by_name = {entry.filename: entry for entry in entries}
            if "release-manifest.json" not in by_name or "checksums.json" not in by_name:
                raise ReleasePackageError("offline package metadata is missing")
            if any(stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK for entry in entries):
                raise ReleasePackageError("offline package cannot contain symlinks")
            if sum(entry.file_size for entry in entries) > MAX_ARCHIVE_BYTES:
                raise ReleasePackageError("offline package expanded size is invalid")
            manifest = validate_release_manifest(
                json.loads(archive.read("release-manifest.json").decode("utf-8"))
            )
            checksums = json.loads(archive.read("checksums.json").decode("utf-8"))
            if (
                not isinstance(checksums, dict)
                or set(checksums) != {"schema_version", "files"}
                or checksums.get("schema_version") != CHECKSUM_SCHEMA
                or not isinstance(checksums.get("files"), dict)
                or set(checksums["files"]) != set(names) - {"checksums.json"}
            ):
                raise ReleasePackageError("offline package checksum manifest is invalid")
            for name, expected in checksums["files"].items():
                if (
                    not isinstance(expected, dict)
                    or set(expected) != {"sha256", "bytes"}
                    or not HASH_RE.fullmatch(str(expected.get("sha256", "")))
                    or isinstance(expected.get("bytes"), bool)
                    or not isinstance(expected.get("bytes"), int)
                    or expected["bytes"] <= 0
                ):
                    raise ReleasePackageError("offline package checksum entry is invalid")
                digest = hashlib.sha256()
                size = 0
                with archive.open(name) as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        size += len(chunk)
                        digest.update(chunk)
                        if size <= MAX_TEXT_SCAN_BYTES:
                            _scan_bytes(chunk, name)
                if size != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
                    raise ReleasePackageError("offline package checksum mismatch")
            source_name = f"source/robot-scope-{manifest['git_commit']}.tar"
            required = {
                source_name,
                "dependencies/python-install-manifest.txt",
                "dependencies/package-lock.json",
                "tools/robot_scope_doctor.py",
                "tools/robot_scope_acceptance.py",
                "runbooks/WP08_RELEASE_LOCK_ROLLBACK_RUNBOOK.md",
            }
            if (
                not required.issubset(names)
                or not any(name.startswith("models/active/") for name in names)
                or not any(name.startswith("service-examples/") for name in names)
                or not all(
                    f"acceptance/{report_id}.json" in names
                    for report_id in manifest["acceptance_report_ids"]
                )
            ):
                raise ReleasePackageError("offline package is incomplete")
            try:
                install_text = archive.read(
                    "dependencies/python-install-manifest.txt"
                ).decode("utf-8")
            except UnicodeError as exc:
                raise ReleasePackageError("Python install manifest is unreadable") from exc
            if PRIVATE_INPUT_SECRET_RE.search(install_text) or URL_USERINFO_RE.search(install_text):
                raise ReleasePackageError(
                    "credential-like content rejected in Python install manifest"
                )
            try:
                source_members = set()
                with archive.open(source_name) as source, tarfile.open(
                    fileobj=source, mode="r|"
                ) as source_tar:
                    for member in source_tar:
                        member_name = _safe_archive_name(member.name)
                        source_members.add(member_name)
                        blocked_runtime = (
                            member_name.startswith("runtime/")
                            or member_name.startswith("workspaces/")
                            or PurePosixPath(member_name).suffix.lower()
                            in {".bag", ".db3", ".mcap", ".pcd"}
                        )
                        basename = PurePosixPath(member_name).name
                        blocked_env = basename == ".env" or (
                            basename.startswith(".env.") and not basename.endswith(".example")
                        )
                        if member.issym() or member.islnk() or blocked_runtime or blocked_env:
                            raise ReleasePackageError(
                                "verified source archive contains runtime, secret, or linked content"
                            )
                if not set(REQUIRED_REPOSITORY_FILES).issubset(source_members):
                    raise ReleasePackageError("verified source archive is incomplete")
            except tarfile.TarError as exc:
                raise ReleasePackageError("verified source archive is unreadable") from exc
            supervised_observed: set[str] = set()
            supervised_passed: set[str] = set()
            for report_id in manifest["acceptance_report_ids"]:
                try:
                    report = json.loads(
                        archive.read(f"acceptance/{report_id}.json").decode("utf-8")
                    )
                except (UnicodeError, json.JSONDecodeError) as exc:
                    raise ReleasePackageError("acceptance evidence is unreadable") from exc
                observed, passed = _validate_acceptance_report(report, manifest["git_commit"])
                supervised_observed.update(observed)
                supervised_passed.update(passed)
            if not supervised_observed or supervised_observed - supervised_passed:
                raise ReleasePackageError("required supervised acceptance evidence is incomplete")
            return {
                "ok": True,
                "release_id": manifest["release_id"],
                "git_commit": manifest["git_commit"],
                "files": len(names),
                "models": dict(manifest["active_model_ids"]),
            }
    except (OSError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise ReleasePackageError("offline package is unreadable") from exc
