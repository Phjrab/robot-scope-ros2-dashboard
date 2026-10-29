"""Private bounded display assets; publication hashes once, polling returns refs."""

import hashlib
import secrets

from robot_dashboard.expansion_contracts import ContractError
from robot_dashboard.expansion_contracts.messages import integer, token


class SceneAssets:
    """Owned by the scene lock. Bytes are display-only, never solver/safety inputs."""

    def __init__(
        self, max_bytes=8 * 1024 * 1024, max_asset_bytes=2 * 1024 * 1024, max_items=8
    ):
        integer(max_bytes, "asset store limit", 1, 32 * 1024 * 1024)
        integer(max_asset_bytes, "asset byte limit", 1, max_bytes)
        integer(max_items, "asset count limit", 1, 32)
        self.max_bytes, self.max_asset_bytes, self.max_items = (
            max_bytes,
            max_asset_bytes,
            max_items,
        )
        self.items = {}

    def clear(self):
        self.items.clear()

    def publish(self, role, source, content, *, media_type="application/octet-stream"):
        if role not in {"saved_reference_cloud", "live_cloud", "costmap"}:
            raise ContractError("unsupported scene asset role")
        token(source)
        if (
            type(content) is not bytes
            or not content
            or len(content) > self.max_asset_bytes
        ):
            raise ContractError("scene asset byte limit")
        if media_type not in {"application/octet-stream", "application/json"}:
            raise ContractError("unsupported scene asset media type")
        key = (role, source)
        others = [v for k, v in self.items.items() if k != key]
        if (
            len(others) + 1 > self.max_items
            or sum(len(v[1]) for v in others) + len(content) > self.max_bytes
        ):
            raise ContractError("scene asset store bound")
        revision = hashlib.sha256(content).hexdigest()
        prior = self.items.get(key)
        if (
            prior
            and prior[0]["revision"] == revision
            and prior[0]["media_type"] == media_type
        ):
            return dict(prior[0])
        ref = {
            "id": secrets.token_hex(12),
            "revision": revision,
            "role": role,
            "source": source,
            "bytes": len(content),
            "media_type": media_type,
            "usage": "DISPLAY_ONLY",
        }
        self.items[key] = (ref, content)
        return dict(ref)

    def refs(self):
        return [dict(v[0]) for v in self.items.values()]

    def get(self, asset_id, revision):
        for ref, content in self.items.values():
            if ref["id"] == asset_id and ref["revision"] == revision:
                return content, ref["media_type"]
        raise KeyError("scene asset not found or revision retired")
