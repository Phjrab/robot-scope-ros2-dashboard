"""DI catalogue: request identities never become filenames or URLs."""

from dataclasses import dataclass, field
import copy
from typing import Callable

from robot_dashboard.expansion_contracts import ContractError, MapSourceDescriptor
from robot_dashboard.expansion_contracts.messages import ID, token
from robot_dashboard.pcd_editing.store import SourceAsset, _digest


class Conflict(ContractError):
    pass


class Busy(Conflict):
    pass


@dataclass(frozen=True)
class ResolvedSource:
    descriptor: MapSourceDescriptor
    asset: SourceAsset
    # Node -> direct parents, including this source node. Trusted metadata only.
    lineage: dict = field(default_factory=dict)
    semantic_masks: tuple = ()


def validate_dag(sources):
    graph = {}
    for s in sources:
        g = s.lineage or {s.descriptor.key: []}
        if s.descriptor.key not in g:
            raise Conflict("source missing from provenance DAG")
        for node, parents in g.items():
            if (
                not isinstance(node, str)
                or not isinstance(parents, list)
                or len(set(parents)) != len(parents)
            ):
                raise Conflict("invalid provenance DAG")
            if node in graph and graph[node] != parents:
                raise Conflict("conflicting provenance node")
            graph[node] = parents
    if len(graph) > 1024:
        raise Conflict("provenance DAG exceeds limit")
    visiting, done = set(), {}

    def walk(node):
        if node in visiting:
            raise Conflict("provenance cycle")
        if node not in graph:
            raise Conflict("incomplete provenance DAG")
        if node not in done:
            visiting.add(node)
            ancestors = {node}
            for parent in graph[node]:
                ancestors |= walk(parent)
            visiting.remove(node)
            done[node] = ancestors
        return done[node]

    seen = set()
    for s in sources:
        ancestry = walk(s.descriptor.key)
        if seen & ancestry:
            raise Conflict("duplicate ancestor across fusion inputs")
        seen |= ancestry
    return copy.deepcopy(graph)


class CatalogueAdapter:
    def __init__(
        self,
        list_ids: Callable,
        resolver: Callable,
        preview: Callable | None = None,
        *,
        max_sources=128,
        max_bytes=256 * 1024**2,
    ):
        if (
            type(max_sources) is not int
            or not 1 <= max_sources <= 1024
            or not 0 < max_bytes <= 256 * 1024**2
        ):
            raise ValueError("invalid catalogue bounds")
        self.list_ids, self.resolver, self.preview_provider = (
            list_ids,
            resolver,
            preview,
        )
        self.max_sources, self.max_bytes = max_sources, max_bytes

    def resolve(self, map_id):
        token(map_id, "map ID", ID)
        s = self.resolver(map_id)
        if not isinstance(s, ResolvedSource) or not isinstance(s.asset, SourceAsset):
            raise ContractError(
                "trusted resolver must supply ResolvedSource/SourceAsset"
            )
        d = MapSourceDescriptor.from_dict(s.descriptor.to_dict())
        if d.map_id != map_id or any(
            getattr(s.asset, k) != getattr(d, k)
            for k in ("map_id", "revision", "frame_id", "units", "asset_role")
        ):
            raise Conflict("catalogue identity mismatch")
        if _digest(s.asset.path, self.max_bytes) != d.sha256:
            raise Conflict("full-source checksum drift")
        return ResolvedSource(
            d, s.asset, copy.deepcopy(s.lineage), copy.deepcopy(s.semantic_masks)
        )

    def pinned(self, request):
        result = tuple(self.resolve(d["map_id"]) for d in request.sources)
        if [s.descriptor.to_dict() for s in result] != request.sources:
            raise Conflict("catalogue descriptors changed")
        validate_dag(result)
        return result

    def list(self):
        ids = []
        for map_id in self.list_ids():
            if len(ids) >= self.max_sources:
                break
            ids.append(map_id)
        return [self.resolve(i).descriptor.to_dict() for i in ids]

    def preview(self, map_id):
        source = self.resolve(map_id)
        # Fixed, server-owned provider only. No private paths in this return value.
        from robot_dashboard.expansion_contracts import canonical

        value = (
            self.preview_provider(source.descriptor) if self.preview_provider else None
        )
        canonical(value, 32 * 1024)
        return copy.deepcopy(value)
