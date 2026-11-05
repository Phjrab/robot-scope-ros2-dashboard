"""Load an explicitly provisioned private review copy, without operational ports."""
import json
import os
from pathlib import Path
import stat


def _owned_directory(path):
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("review directory must be canonical")
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("review directory must be owner-only")


def configured_review_inputs(environ):
    if environ.get("ROBOT_SCOPE_EXPANSION_MULTIMAP") != "1":
        return None
    value = environ.get("ROBOT_SCOPE_EXPANSION_REVIEW_WORKSPACE")
    if not value:
        return None
    from .review_owner import ReviewInputs

    path = Path(value)

    def maps_factory():
        from robot_dashboard.saved_maps import SavedMapCatalog
        from .catalogue import compose_maps, SavedCataloguePort

        _owned_directory(path.parent)
        info = path.lstat()
        if (path.resolve() != path or not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 512 * 1024):
            raise ValueError("invalid private review workspace manifest")
        data = json.loads(path.read_bytes())
        if (set(data) != {"schema", "catalogue_root", "bundle_root", "metadata"}
                or data["schema"] != "robot-scope.review-workspace.v1"):
            raise ValueError("unsupported review workspace")
        sources, bundles = Path(data["catalogue_root"]), Path(data["bundle_root"])
        # Distinct fixed children: no operator catalogue or path callback is wired.
        if sources != path.parent / "sources" or bundles != path.parent / "bundles":
            raise ValueError("review roots must be separate fixed workspace children")
        _owned_directory(sources)
        if bundles.exists() or bundles.is_symlink():
            _owned_directory(bundles)
        metadata = data["metadata"]
        if not isinstance(metadata, dict) or len(metadata) > 128:
            raise ValueError("invalid bounded review metadata")
        required = {"map_id", "revision", "sha256", "frame_id", "units",
                    "evidence_kind", "source_epoch", "display_name"}
        for map_id, row in metadata.items():
            if (not isinstance(row, dict) or not required.issubset(row)
                    or row["map_id"] != map_id or row["evidence_kind"] not in {"REPLAY", "SYNTHETIC"}):
                raise ValueError("source qualification is incomplete")
            for name in ("frame_id", "source_epoch"):
                if str(row[name]).upper() in {"", "UNKNOWN", "UNAVAILABLE", "UNVERIFIED", "NONE"}:
                    raise ValueError("source qualification is unavailable")
        saved = SavedMapCatalog([sources])
        port = SavedCataloguePort(saved, metadata.get)
        for map_id in metadata:
            port.resolve(map_id)
        return compose_maps(saved, metadata.get, bundles)

    return ReviewInputs(maps_factory=maps_factory)
