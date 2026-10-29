"""Latest-only read-only observations; bounded detached history, explicit fences."""

from collections import deque
import copy
import threading
import time

from robot_dashboard.expansion_contracts import (
    ContractError,
    ObstacleFrame,
    CollisionAssessment,
    ScenePacket,
    canonical,
)
from robot_dashboard.expansion_contracts.messages import (
    Observation,
    integer,
    token,
    ID,
    HASH,
)

SLOTS = {
    "robot_pose",
    "obstacle_frame",
    "global_path",
    "controller_local_trajectory",
    "costmap_snapshot",
    "collision_assessment",
}


class SceneSnapshotService:
    def __init__(
        self,
        map_binding,
        *,
        stream_epoch="scene-0",
        host_clock_id="c1-host",
        max_history=16,
        max_sample_bytes=16 * 1024,
        clock=time.monotonic_ns,
    ):
        integer(max_history, "scene history", 1, 128)
        integer(max_sample_bytes, "sample byte limit", 1024, 128 * 1024)
        self._lock = threading.RLock()
        self.clock, self.host_clock_id = clock, token(host_clock_id)
        self.max_sample_bytes = max_sample_bytes
        self._history = deque(maxlen=max_history)
        self._retired_epochs = {slot: set() for slot in SLOTS}
        self._latest, self._sequence, self.dropped = {}, 0, 0
        self.reset(map_binding, stream_epoch)

    def reset(self, map_binding, stream_epoch):
        if not isinstance(map_binding, dict) or set(map_binding) != {
            "map_id",
            "revision",
            "generation",
        }:
            raise ContractError("map binding required")
        token(map_binding["map_id"], pattern=ID)
        token(map_binding["revision"], pattern=HASH)
        integer(map_binding["generation"], "map generation")
        token(stream_epoch)
        with self._lock:
            if (
                hasattr(self, "map_binding")
                and map_binding["generation"] <= self.map_binding["generation"]
            ):
                raise ContractError("map reset requires increasing generation")
            self.map_binding, self.stream_epoch = (
                copy.deepcopy(map_binding),
                stream_epoch,
            )
            self._latest.clear()
            self._retired_epochs = {slot: set() for slot in SLOTS}
            self._history.clear()
            self._sequence = 0

    def reset_source(self, slot, new_epoch):
        if slot not in SLOTS:
            raise ContractError("unknown scene source")
        token(new_epoch)
        with self._lock:
            previous = self._latest.pop(slot, None)
            retired = self._retired_epochs[slot]
            if previous:
                retired.add(previous["source_epoch"])
            if new_epoch in retired or len(retired) > 64:
                raise ContractError(
                    "stale epoch or epoch history bound; reset map generation"
                )
            # A source reset clears every cross-source pairing until fresh packets arrive.
            self._latest.clear()
            self._history.clear()
            self._latest[slot] = {
                "source_epoch": new_epoch,
                "sequence": -1,
                "_pending": True,
            }

    def ingest(self, slot, payload):
        if slot not in SLOTS:
            raise ContractError("unknown scene source")
        canonical(payload, self.max_sample_bytes)
        if slot == "obstacle_frame":
            m = ObstacleFrame.from_dict(payload).to_dict()
        elif slot == "collision_assessment":
            m = CollisionAssessment.from_dict(payload).to_dict()
        else:
            keys = {
                "schema_version",
                "evidence_kind",
                "producer",
                "sequence",
                "source_epoch",
                "frame_key",
                "stamp_ns",
                "clock_domain",
                "host_clock_id",
                "received_monotonic_ns",
                "map_binding",
            }
            if set(payload) != keys | {"data", "health"}:
                raise ContractError("read-only scene source envelope differs")
            Observation.from_dict({k: payload[k] for k in keys})
            m = copy.deepcopy(payload)
        with self._lock:
            previous = self._latest.get(slot)
            if (
                m["map_binding"] != self.map_binding
                or m["source_epoch"] in self._retired_epochs[slot]
                or (
                    previous
                    and (
                        m["source_epoch"] != previous["source_epoch"]
                        or m["sequence"] <= previous["sequence"]
                    )
                )
            ):
                self.dropped += 1
                return False
            if (
                sum(len(canonical(v)) for k, v in self._latest.items() if k != slot)
                + len(canonical(m))
                > 80 * 1024
            ):
                self.dropped += 1
                return False
            self._latest[slot] = m
            self._sequence += 1
            # Ring stores metadata only; samples stay latest-only, no persistent request ledger.
            self._history.append(
                {
                    "slot": slot,
                    "sequence": m["sequence"],
                    "source_epoch": m["source_epoch"],
                }
            )
            return True

    def snapshot(self):
        with self._lock:
            now, values, sources = self.clock(), {}, {}
            for slot in SLOTS:
                m = self._latest.get(slot)
                if m and m.get("_pending"):
                    m = None
                values[slot] = copy.deepcopy(m)
                if m:
                    age = (
                        (now - m["received_monotonic_ns"]) / 1e6
                        if m["host_clock_id"] == self.host_clock_id
                        and now >= m["received_monotonic_ns"]
                        else None
                    )
                    sources[slot] = {
                        "source_epoch": m["source_epoch"],
                        "sequence": m["sequence"],
                        "stamp_ns": m["stamp_ns"],
                        "clock_domain": m["clock_domain"],
                        "host_clock_id": m["host_clock_id"],
                        "received_age_ms": age,
                        "sensor_age_ms": None,
                        "evidence_kind": m["evidence_kind"],
                        "health": m.get("health", m.get("freshness")),
                        "calibration_status": "UNKNOWN"
                        if slot == "obstacle_frame" and m["calibration_id"] is None
                        else "SUPPLIED",
                    }
            # Collision is retained only if its exact obstacle reference belongs to current packet.
            c, o = values["collision_assessment"], values["obstacle_frame"]
            validity = c["validity_interval"] if c else {}
            valid_time = bool(
                validity
                and validity["host_clock_id"] == self.host_clock_id
                and validity["start_monotonic_ns"]
                <= now
                <= validity["end_monotonic_ns"]
            )
            if c and (
                not valid_time
                or not o
                or c["obstacle_frame_ref"]
                != {"source_epoch": o["source_epoch"], "sequence": o["sequence"]}
            ):
                values["collision_assessment"] = None
                sources["collision_assessment"]["health"] = {
                    "state": "REFERENCE_OR_VALIDITY_UNKNOWN"
                }
            kinds = {m["evidence_kind"] for m in values.values() if m}
            # Mixed evidence is never silently labelled live.
            evidence = (
                "SYNTHETIC"
                if not kinds or "SYNTHETIC" in kinds
                else ("REPLAY" if "REPLAY" in kinds else "LIVE")
            )
            packet = ScenePacket(
                schema_version="0.1",
                evidence_kind=evidence,
                producer="c1-scene",
                sequence=self._sequence,
                source_epoch=self.stream_epoch,
                map_binding=copy.deepcopy(self.map_binding),
                stream_epoch=self.stream_epoch,
                sources=sources,
                **values,
            )
            return packet.to_dict()

    def metrics(self):
        with self._lock:
            return {
                "history_size": len(self._history),
                "history_limit": self._history.maxlen,
                "latest_size": len(self._latest),
                "dropped": self.dropped,
                "persistent_ledger_writes": 0,
            }
