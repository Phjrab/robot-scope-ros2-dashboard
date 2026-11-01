"""Read-only SavedMapCatalog bridge plus a separate immutable review registry.

Acquisition metadata is supplied by the server owner, never an HTTP descriptor.
Unqualified legacy files are excluded rather than assigned a synthetic session.
"""
from pathlib import Path
from dataclasses import replace
import numpy as np

from robot_dashboard.expansion_contracts import MapSourceDescriptor
from robot_dashboard.expansion_services.catalogue import CatalogueAdapter, ResolvedSource
from robot_dashboard.expansion_services.errors import Conflict
from robot_dashboard.pcd_editing.pcd import _read_header
from robot_dashboard.pcd_editing.store import _digest, _open_regular


class SavedCataloguePort:
    def __init__(self, saved_maps, metadata_provider):
        self.saved_maps = saved_maps
        self.metadata_provider = metadata_provider
        self.store = None
        self.adapter = CatalogueAdapter(self.list_ids, self.resolve, self.preview)

    def list_ids(self):
        ids = [row["id"] for row in self.saved_maps.list_snapshot()["maps"]
               if row["format"] == "pcd-binary" and self.metadata_provider(row["id"]) is not None]
        if self.store is not None:
            ids.extend(item["id"] for item in self.store.list())
        return ids

    def resolve(self, map_id):
        metadata = self.metadata_provider(map_id)
        if metadata is None:
            if self.store is not None:
                source = self.store.reload(map_id)
                name = self.store.get(map_id)["name"]
                return replace(source, descriptor=replace(source.descriptor,
                    acquisition={**source.descriptor.acquisition, "display_name": name}))
            raise FileNotFoundError("qualified source unavailable")
        # Existing owner resolver performs private path lookup and revision fencing.
        asset = self.saved_maps._pcd_edit_source_asset(map_id)
        digest = _digest(asset.path, self.saved_maps.max_file_bytes)
        if any(metadata.get(key) != value for key, value in {
            "map_id": asset.map_id, "revision": asset.revision, "sha256": digest,
            "frame_id": asset.frame_id, "units": asset.units,
        }.items()):
            raise Conflict("source qualification changed", code="STALE_SOURCE_REVISION")
        with _open_regular(asset.path, self.saved_maps.max_file_bytes) as stream:
            _, _, _, count, fields = _read_header(stream, asset.path.stat().st_size, 20_000_000)
        descriptor = MapSourceDescriptor(
            schema_version="0.1", evidence_kind=metadata["evidence_kind"],
            producer="i0-saved-catalogue", sequence=0, source_epoch=metadata["source_epoch"],
            map_id=asset.map_id, revision=asset.revision, sha256=digest,
            frame_id=asset.frame_id, units=asset.units, asset_role="full_source",
            mapping_session_id=metadata.get("mapping_session_id"),
            gravity_or_plane=metadata.get("gravity_or_plane"),
            point_count=count, point_schema=fields,
            acquisition={"origin": "qualified saved catalogue", "display_name": metadata["display_name"]},
        )
        lineage = metadata.get("lineage", {})
        if asset.edit_history and not lineage:
            raise Conflict("edited source needs original ancestry", code="INVALID_PROVENANCE")
        return ResolvedSource(descriptor, asset, lineage)

    def preview(self, descriptor):
        source = self.resolve(descriptor.map_id)
        if source.descriptor != descriptor:
            raise Conflict("preview source changed", code="STALE_SOURCE_REVISION")
        points = []
        with _open_regular(source.asset.path, 256 * 1024**2) as stream:
            _, _, dtype, count, _ = _read_header(stream, source.asset.path.stat().st_size, 20_000_000)
            offset = stream.tell()
            for index in np.linspace(0, count - 1, min(count, 160), dtype=int):
                stream.seek(offset + int(index) * dtype.itemsize)
                record = np.frombuffer(stream.read(dtype.itemsize), dtype=dtype, count=1)
                xyz = [float(record[name][0]) for name in ("x", "y", "z")]
                if all(np.isfinite(xyz)):
                    points.extend(xyz)
        if _digest(source.asset.path, 256 * 1024**2) != descriptor.sha256:
            raise Conflict("preview source changed", code="SOURCE_CONTENT_CHANGED")
        return {"schema": "robot-scope.multimap-ui.v1", "units": "m",
                "input_pin": {"id": descriptor.map_id, "revision": descriptor.revision,
                              "sha256": descriptor.sha256,
                              "session_id": descriptor.mapping_session_id or f"unverified:{descriptor.map_id}"},
                "points": points}


def compose_maps(saved_maps, metadata_provider, private_root):
    from robot_dashboard.expansion_contracts import FusionProposal
    from robot_dashboard.expansion_services.export import BundleStore
    from robot_dashboard.expansion_services.jobs import FusionJobManager
    from robot_dashboard.multimap_core.contract_adapter import solve_contract

    port = SavedCataloguePort(saved_maps, metadata_provider)
    store = BundleStore(Path(private_root), port.adapter)
    port.store = store

    def solve(request, sources, cancel, progress, *, job_id):
        paths = {source.descriptor.map_id: source.asset.path for source in sources}
        return solve_contract(request, lambda d: paths[d["map_id"]], FusionProposal,
                              job_id=job_id, cancel_token=cancel,
                              progress=lambda event: progress(min(.95, event["completed_pairs"])))

    return port.adapter, FusionJobManager(port.adapter, solve, store), store
