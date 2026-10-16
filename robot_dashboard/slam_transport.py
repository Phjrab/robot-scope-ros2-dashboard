"""Opt-in, per-connection references for unchanged SLAM visualization layers.

Only delivery changes: snapshots, source stamps and estimator inputs are intact.
Legacy clients still receive complete frames. A new connection/context starts
with full geometry, and an empty layer clears its reference immediately.
"""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from .slam_sessions import SlamError


class SlamGeometryTransport:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._context: tuple[Any, ...] | None = None
        self._layers: dict[str, tuple[str, dict[str, Any]]] = {}
        self._sequence = 0

    def encode(self, frame: dict[str, Any]) -> str:
        if not self.enabled:
            return self._wire(frame)
        context = tuple(frame.get(key) for key in
                        ("engine_id", "session_id", "generation", "map_epoch", "frame_id"))
        valid = (type(context[2]) is int and context[2] >= 0
                 and all(isinstance(context[i], str) and context[i] for i in (0, 1, 3, 4)))
        if not valid or context != self._context:
            self._layers.clear()
            self._context = context if valid else None
        if not valid:
            return self._wire(frame)
        result = dict(frame)
        updates: dict[str, dict[str, str]] = {}
        for name in ("global_map", "trajectory"):
            layer = frame.get(name)
            if not isinstance(layer, dict):
                self._layers.pop(name, None)
                continue
            previous = self._layers.get(name)
            # Equal counts, timestamps or snapshot IDs alone are insufficient:
            # corrections can replace coordinates without changing those fields.
            if previous is not None and previous[1] == layer:
                token = previous[0]
                result[name] = None
                kind = "reference"
            else:
                self._sequence += 1
                token = str(self._sequence)
                self._layers[name] = (token, deepcopy(layer))
                kind = "full"
            updates[name] = {"kind": kind, "token": token}
        result["geometry_updates"] = {"version": 1, "layers": updates}
        return self._wire(result)

    @staticmethod
    def _wire(frame: dict[str, Any]) -> str:
        wire = json.dumps(frame, allow_nan=False, separators=(",", ":"))
        if len(wire.encode("utf-8")) > 8 * 1024**2:
            raise SlamError("VISUALIZATION_LIMIT")
        return wire


def encode_stream_frame(manager: Any, transport: SlamGeometryTransport) -> str:
    """Run source sampling and JSON work together off the ASGI event loop."""
    return transport.encode(manager.frame())
