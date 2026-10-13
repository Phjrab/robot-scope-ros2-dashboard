#!/usr/bin/env python3
"""Explicitly rebind copied map sidecars to the current catalog identities.

Capture runs on the source host. Adaptation runs only against copied target
files and requires a byte-exact preservation root. Map pixels/clouds and
authoring geometry are never changed; existing revision validation is reused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robot_dashboard.map_annotations import MapAnnotationFormatError, annotation_revision, normalize_annotation_document, parse_annotation_document, serialized_annotation_document
from robot_dashboard.map_lineage import CONVERSION_KEYS, build_family_document, parse_family_document, serialize_family_document
from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapFormatError


SCHEMA = "robot-scope.map-identity-migration/v1"


class IdentityMigrationError(ValueError):
    pass


def _root(path: Path) -> Path:
    if not path.is_absolute() or path == Path("/") or path.resolve(strict=True) != path or not path.is_dir():
        raise IdentityMigrationError("map roots must be real absolute directories")
    return path


def _digest(path: Path) -> str:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or path.resolve(strict=True) != path:
        raise IdentityMigrationError("artifacts must be regular files without links")
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise IdentityMigrationError("artifact changed while opening")
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise IdentityMigrationError("artifact changed while hashing")
    return digest.hexdigest()


def _relative(value: str) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or path.as_posix() != value or any(p.startswith(".") for p in path.parts):
        raise IdentityMigrationError("artifact paths must be safe relative paths")
    return path


def _catalog(root: Path) -> SavedMapCatalog:
    return SavedMapCatalog([root], managed_roots=[root], max_files=2000, max_depth=3)


def _rounded_pi_canonicalization(raw: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
    """Recognize only the historical six-decimal pi serialization defect.

    The original content hash must be authentic. All authoring fields except
    the already-supported pi rounding margin must survive normalization exactly.
    """
    revision = annotation_revision(map_id=raw["map_id"], map_revision=raw["map_revision"],
                                  points=raw["points"], polygons=raw["polygons"])
    if raw["annotation_revision"] != revision or raw["revision"] != revision:
        raise IdentityMigrationError("source annotation content hash is invalid")
    if raw["polygons"] != normalized["polygons"] or len(raw["points"]) != len(normalized["points"]):
        raise IdentityMigrationError("source annotation canonicalization would change authoring geometry")
    changed = []
    for index, (old, new) in enumerate(zip(raw["points"], normalized["points"])):
        if old == new:
            continue
        yaw = old.get("pose", {}).get("yaw")
        if yaw not in {round(math.pi, 6), round(-math.pi, 6)}:
            raise IdentityMigrationError("source annotation change is not the historical rounded-pi defect")
        corrected = {**old, "pose": {**old["pose"], "yaw": math.copysign(math.pi, yaw)}}
        if corrected != new:
            raise IdentityMigrationError("source annotation canonicalization would change authoring fields")
        changed.append({"point_index": index, "source_yaw": yaw, "canonical_yaw": new["pose"]["yaw"]})
    if not changed:
        raise IdentityMigrationError("source annotation mismatch has no recognized rounded-pi cause")
    return {"source_validation": "FAIL", "reason": "historical rounded-pi content revision mismatch",
            "source_annotation_revision": revision, "canonical_source_revision": normalized["annotation_revision"],
            "changes": changed}


def capture(root: Path, *, canonicalize_rounded_pi: bool = False) -> dict[str, Any]:
    root = _root(root)
    catalog = _catalog(root)
    records = catalog._scan()
    maps = []
    artifacts: dict[str, str] = {}
    families = {}
    annotations = {}
    canonicalizations = {}
    for record in records:
        relative = record.path.relative_to(root).as_posix()
        maps.append({"path": relative, "kind": record.kind, "id": record.map_id, "revision": record.revision})
        for path in (record.path, record.auxiliary_path):
            if path is not None:
                artifacts[path.relative_to(root).as_posix()] = _digest(path)
        if record.kind != "occupancy2d":
            continue
        family = catalog._lineage_path(record)
        if family.exists():
            # This rejects stale SOURCE pins before any target rebinding.
            catalog.resolve_navigation_map(record.map_id, record.revision)
            name = family.relative_to(root).as_posix()
            families[name] = parse_family_document(json.loads(family.read_text(encoding="utf-8")))
            artifacts[name] = _digest(family)
        annotation = catalog._annotation_path(record)
        if annotation.exists():
            name = annotation.relative_to(root).as_posix()
            artifacts[name] = _digest(annotation)
            raw = json.loads(annotation.read_text(encoding="utf-8"))
            try:
                catalog.annotations(record.map_id)
            except SavedMapFormatError as exc:
                if (not canonicalize_rounded_pi or not isinstance(exc.__cause__, MapAnnotationFormatError)
                        or str(exc.__cause__) != "annotation revision does not match its content"):
                    raise
                geometry = catalog._annotation_geometry(record)
                normalized = normalize_annotation_document(map_id=raw["map_id"], map_revision=raw["map_revision"],
                             points=raw["points"], polygons=raw["polygons"], geometry=geometry, identifier_factory=lambda: "")
                canonicalizations[name] = _rounded_pi_canonicalization(raw, normalized)
                # Rebuilt source derivative must pass the existing strict parser.
                parse_annotation_document(json.loads(serialized_annotation_document(normalized)), geometry=geometry)
            if _digest(annotation) != artifacts[name]:
                raise IdentityMigrationError("source annotation changed during capture")
            annotations[name] = raw
    by_id = {record["id"]: record for record in maps}
    for family in families.values():
        source = by_id.get(family["source"]["pcd_map_id"])
        if source is None or source["revision"] != family["source"]["pcd_revision"] or source["kind"] != "pointcloud3d":
            raise IdentityMigrationError("source family references a missing or stale PCD")
    return {"schema": SCHEMA, "source_root": str(root), "maps": maps, "artifacts": artifacts,
            "families": families, "annotations": annotations, "annotation_canonicalizations": canonicalizations}


def plan(source: dict[str, Any], original: Path, target: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    original, target = _root(original), _root(target)
    if original == target or original in target.parents or target in original.parents:
        raise IdentityMigrationError("preservation and target roots must be separate")
    if source.get("schema") != SCHEMA or not isinstance(source.get("maps"), list) or not isinstance(source.get("artifacts"), dict):
        raise IdentityMigrationError("source identity capture is invalid")
    for name, digest in source["artifacts"].items():
        relative = _relative(name)
        if _digest(original / relative) != digest or _digest(target / relative) != digest:
            raise IdentityMigrationError("preservation or target no longer matches source bytes")
    catalog = _catalog(target)
    current = {record.path.relative_to(target).as_posix(): record for record in catalog._scan()}
    identity = {}
    records = []
    for old in source["maps"]:
        name = _relative(old["path"]).as_posix()
        new = current.get(name)
        if new is None or new.kind != old["kind"] or old["id"] in identity:
            raise IdentityMigrationError("source and target catalog members differ")
        identity[old["id"]] = (old, new)
        records.append({"path": name, "source_id": old["id"], "source_revision": old["revision"],
                        "target_id": new.map_id, "target_revision": new.revision})
    if len(current) != len(records):
        raise IdentityMigrationError("target contains unlisted maps")
    outputs = {}
    family_revisions = {}
    pending = dict(source["families"])
    known_revisions = {family["family_revision"] for family in pending.values()}
    historical_parents = set()
    while pending:
        progress = False
        for name, raw in list(pending.items()):
            if raw != json.loads((original / _relative(name)).read_text(encoding="utf-8")):
                raise IdentityMigrationError("captured family content differs from preserved source")
            family = parse_family_document(raw)
            parent = family["derived_from_family_revision"]
            if parent in known_revisions and parent not in family_revisions:
                continue
            if parent is not None and parent not in known_revisions:
                historical_parents.add(parent)
            old_pcd, pcd = identity[family["source"]["pcd_map_id"]]
            old_occupancy, occupancy = identity[family["occupancy"]["map_id"]]
            if (old_pcd["revision"] != family["source"]["pcd_revision"]
                    or old_occupancy["revision"] != family["occupancy"]["map_revision"]):
                raise IdentityMigrationError("source family pin is stale")
            updated = build_family_document(
                family_id=family["family_id"], mapping_session_id=family["source"]["mapping_session_id"],
                pcd_map_id=pcd.map_id, pcd_revision=pcd.revision, source_frame_id=family["source"]["frame_id"],
                occupancy_map_id=occupancy.map_id, occupancy_revision=occupancy.revision,
                occupancy_frame_id=family["occupancy"]["frame_id"], resolution=family["occupancy"]["resolution"],
                width=family["occupancy"]["width"], height=family["occupancy"]["height"], origin=family["occupancy"]["origin"],
                parameters={key: family["conversion"][key] for key in CONVERSION_KEYS}, created_at=family["created_at"],
                derived_from_family_revision=family_revisions.get(parent, parent),
            )
            outputs[name] = serialize_family_document(updated)
            family_revisions[family["family_revision"]] = updated["family_revision"]
            del pending[name]
            progress = True
        if not progress:
            raise IdentityMigrationError("source family lineage contains a cycle")
    annotation_revisions = {}
    for name, raw in source["annotations"].items():
        if raw != json.loads((original / _relative(name)).read_text(encoding="utf-8")):
            raise IdentityMigrationError("captured annotations differ from preserved source")
        old, new = identity[raw["map_id"]]
        if old["revision"] != raw["map_revision"]:
            raise IdentityMigrationError("source annotation pin is stale")
        geometry = catalog.route_geometry(new.map_id, new.revision)
        source_geometry = replace(geometry, map_id=old["id"], revision=old["revision"])
        try:
            parse_annotation_document(raw, geometry=source_geometry)
            if name in source.get("annotation_canonicalizations", {}):
                raise IdentityMigrationError("annotation canonicalization record is inconsistent")
        except MapAnnotationFormatError as exc:
            if str(exc) != "annotation revision does not match its content" or name not in source.get("annotation_canonicalizations", {}):
                raise
            normalized = normalize_annotation_document(map_id=old["id"], map_revision=old["revision"],
                         points=raw["points"], polygons=raw["polygons"], geometry=source_geometry, identifier_factory=lambda: "")
            if _rounded_pi_canonicalization(raw, normalized) != source["annotation_canonicalizations"][name]:
                raise IdentityMigrationError("annotation canonicalization provenance differs")
        document = normalize_annotation_document(map_id=new.map_id, map_revision=new.revision,
                    points=raw["points"], polygons=raw["polygons"], geometry=geometry, identifier_factory=lambda: "")
        outputs[name] = serialized_annotation_document(document)
        annotation_revisions[raw["annotation_revision"]] = document["annotation_revision"]
    changes = [{"path": name, "source_sha256": source["artifacts"][name],
                "target_sha256": hashlib.sha256(payload).hexdigest()} for name, payload in sorted(outputs.items())]
    report = {"schema": SCHEMA, "status": "PLANNED", "source_root": source["source_root"],
              "preservation_root": str(original), "target_root": str(target), "maps": records,
              "family_revisions": family_revisions, "annotation_revisions": annotation_revisions,
              "historical_parent_revisions": sorted(historical_parents), "changes": changes,
              "source_annotation_canonicalizations": source.get("annotation_canonicalizations", {}),
              "map_payloads_modified": False, "source_modified": False}
    return report, outputs


def _write(path: Path, payload: bytes) -> None:
    if path.parent.resolve(strict=True) != path.parent:
        raise IdentityMigrationError("output directory contains a symlink")
    temporary = path.with_name(path.name + ".migration-" + os.urandom(6).hex())
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def adapt(source: dict[str, Any], original: Path, target: Path, report_path: Path) -> dict[str, Any]:
    if os.path.lexists(report_path):
        raise IdentityMigrationError("provenance report already exists")
    report, outputs = plan(source, original, target)
    report["status"] = "APPLYING"
    _write(report_path, (json.dumps(report, sort_keys=True, indent=2) + "\n").encode())
    applied = []
    try:
        for name, payload in outputs.items():
            if _digest(target / name) != source["artifacts"][name]:
                raise IdentityMigrationError("sidecar changed before adaptation")
            _write(target / name, payload)
            applied.append(name)
        catalog = _catalog(target)
        family_count = annotation_count = 0
        for record in catalog._scan():
            if record.kind == "occupancy2d":
                catalog.resolve_navigation_map(record.map_id, record.revision)
                family_count += int(catalog._lineage_path(record).exists())
                catalog.annotations(record.map_id)
                annotation_count += int(catalog._annotation_path(record).exists())
        for name, digest in source["artifacts"].items():
            if _digest(original / name) != digest or (name not in outputs and _digest(target / name) != digest):
                raise IdentityMigrationError("preserved map payload changed")
        report.update(status="PASS", families_validated=family_count, annotations_validated=annotation_count)
        _write(report_path, (json.dumps(report, sort_keys=True, indent=2) + "\n").encode())
    except Exception:
        for name in reversed(applied):
            if _digest(target / name) != hashlib.sha256(outputs[name]).hexdigest():
                raise IdentityMigrationError("adaptation rollback refused an unrelated file change")
            _write(target / name, (original / name).read_bytes())
        report.update(status="FAIL", sidecar_rollback="PASS")
        _write(report_path, (json.dumps(report, sort_keys=True, indent=2) + "\n").encode())
        raise
    return report


def validate_unreferenced_routes(root: Path) -> dict[str, Any]:
    """Validate the actual imported planners without rewriting their caches.

    Referenced saved-map graphs need a separate authored-graph migration; this
    narrow path rejects them rather than guessing a new cached route identity.
    """
    from robot_dashboard.route_planner.state_store import RoutePlannerStateStore
    from robot_dashboard.route_planner.schematic_session import SchematicSession
    import tempfile

    keys = {"map_id", "map_revision", "annotation_revision", "pcd_map_id", "pcd_revision", "occupancy_map_id", "occupancy_revision", "family_revision"}
    def check(value):
        if isinstance(value, dict):
            if keys.intersection(value):
                raise IdentityMigrationError("saved-map route pins require explicit authored-graph migration")
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)
    root = _root(root)
    documents = list(root.rglob("route-planner.json"))
    for path in documents:
        check(json.loads(path.read_text(encoding="utf-8")))
    state = RoutePlannerStateStore(root).load()
    if state["guidance"]["active"]:
        raise IdentityMigrationError("guidance resumed during validation")
    if (root / "schematic/route-planner.json").exists():
        with tempfile.TemporaryDirectory() as temporary:
            validation = Path(temporary).resolve()
            (validation / "schematic").mkdir(mode=0o700)
            _write(validation / "schematic/route-planner.json", (root / "schematic/route-planner.json").read_bytes())
            schematic = SchematicSession(validation)
            if any(bucket["guidance"]["active"] for bucket in schematic.state["buckets"].values()):
                raise IdentityMigrationError("schematic guidance resumed during validation")
    return {"status": "PASS", "files": len(documents), "saved_map_pins": 0, "guidance_resumed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    capture_parser = sub.add_parser("capture")
    capture_parser.add_argument("--maps-root", type=Path, required=True)
    capture_parser.add_argument("--output", type=Path, required=True)
    capture_parser.add_argument("--canonicalize-rounded-pi", action="store_true",
                                help="record the authenticated historical six-decimal pi defect for an explicit target derivative")
    migrate = sub.add_parser("adapt")
    migrate.add_argument("--maps-root", type=Path, required=True)
    migrate.add_argument("--original-maps", type=Path, required=True)
    migrate.add_argument("--source-capture", type=Path, required=True)
    migrate.add_argument("--report", type=Path, required=True)
    migrate.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "capture":
            if os.path.lexists(args.output):
                raise IdentityMigrationError("source identity output already exists")
            result = capture(args.maps_root, canonicalize_rounded_pi=args.canonicalize_rounded_pi)
            _write(args.output, (json.dumps(result, sort_keys=True, indent=2) + "\n").encode())
            print(json.dumps({"status": "PASS", "maps": len(result["maps"])}))
        else:
            source = json.loads(args.source_capture.read_text(encoding="utf-8"))
            report = adapt(source, args.original_maps, args.maps_root, args.report) if args.apply else plan(source, args.original_maps, args.maps_root)[0]
            print(json.dumps({"status": report["status"], "maps": len(report["maps"]), "sidecars": len(report["changes"])}))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "FAIL", "reason": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
