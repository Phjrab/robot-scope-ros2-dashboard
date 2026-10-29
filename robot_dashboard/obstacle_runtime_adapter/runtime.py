"""Injected D2 -> C1/C3 ports using the existing bounded latest-only worker."""
from copy import deepcopy
from dataclasses import dataclass
import json
import time

from .isolation import RuntimeConfig
from .messages import Identity, Sample

MAX_SCENE_BYTES = 512 * 1024


@dataclass(frozen=True)
class Input:
    identity: Identity
    message: object
    normalize: object
    options: dict
    generation: int


@dataclass(frozen=True)
class Result:
    context: dict
    sample: Sample
    obstacle_frame: dict
    generation: int


class _Pipeline:
    def __init__(self, owner):
        self.owner = owner

    def process(self, item, *, now_s):
        sample = item.normalize(item.message, item.identity, **item.options)
        # D2 performs perception/fusion; C4 never clusters or assigns classes.
        frame = self.owner.d2.process(sample)
        # Validate through C1's injected implementation when available.
        self.owner.validate_obstacle(frame)
        expected = sample.identity
        for name in ("stamp_ns", "clock_domain", "source_epoch", "sequence", "evidence_kind"):
            if frame.get(name) != getattr(expected, name):
                raise ValueError("D2_SOURCE_IDENTITY_CHANGED:" + name)
        if frame.get("frame_key") != expected.packet()["frame_key"] or frame.get("map_binding") != expected.packet()["map_binding"]:
            raise ValueError("D2_FRAME_BINDING_CHANGED")
        if (frame.get("received_monotonic_ns", frame.get("received_ns")) != expected.received_ns
                or frame.get("host_clock_id", frame.get("receipt_clock_id")) != expected.receipt_clock_id
                or frame.get("tf_epoch", expected.tf_epoch) != expected.tf_epoch):
            raise ValueError("D2_RECEIPT_OR_TF_CHANGED")
        # No truncation masquerading as full geometry. Oversize is rejected.
        encoded = json.dumps(frame, allow_nan=False).encode()
        if len(encoded) > MAX_SCENE_BYTES:
            raise ValueError("OBSTACLE_OUTPUT_LIMIT")
        return Result({"processed_s": now_s}, sample, deepcopy(frame), item.generation)


class RuntimeAdapter:
    """One executing + one pending globally; fixed source registry; one scene.

    start/offer/rebind/close run on one owner asyncio loop. A ROS callback hands
    references to that loop using call_soon_threadsafe; it never calls D2.
    The existing owner must not mutate a handed-off message. Creation does not
    import detector/ROS libraries, create threads, or open a source.
    """
    def __init__(self, *, d2, scene_sink, validate_obstacle, source_epochs,
                 binding, receipt_clock_id, config=RuntimeConfig(), clock_ns=time.monotonic_ns,
                 stale_ns=500_000_000):
        if not 0 < len(source_epochs) <= 16 or not 0 < stale_ns <= 10_000_000_000:
            raise ValueError("RUNTIME_BOUNDS_INVALID")
        self.config, self.clock_ns, self.stale_ns = config, clock_ns, stale_ns
        self.d2, self.scene_sink, self.validate_obstacle = d2, scene_sink, validate_obstacle
        self.source_epochs, self.binding = dict(source_epochs), tuple(binding)
        self.receipt_clock_id = receipt_clock_id
        self.generation, self.worker, self.latest_scene = 0, None, None
        self.last = {}
        self.rejected, self.late_results = 0, 0

    def start(self):
        if self.config.mode in {"offline", "dry_run"}:
            raise ValueError("EXPLICIT_EXECUTION_MODE_REQUIRED")
        if self.worker is not None:
            raise ValueError("ALREADY_STARTED")
        from robot_dashboard.competition_traffic.worker import TrafficWorker
        self.worker = TrafficWorker(_Pipeline(self), clock=lambda: self.clock_ns()/1e9,
                                    result_sink=self._result)
        self.worker.start()

    def rebind(self, *, source_epochs, binding):
        if not 0 < len(source_epochs) <= 16:
            raise ValueError("SOURCE_LIMIT")
        self.generation += 1
        self.source_epochs, self.binding = dict(source_epochs), tuple(binding)
        self.last.clear()
        self.latest_scene = None

    def offer_raw(self, message, identity, normalize, **options):
        """Constant-size ingress; layout normalization and D2 execute in worker."""
        now = self.clock_ns()
        last = self.last.get(identity.source_id)
        valid = (self.worker is not None and not self.worker.closed
            and identity.receipt_clock_id == self.receipt_clock_id
            and identity.binding == self.binding
            and self.source_epochs.get(identity.source_id) == identity.source_epoch
            and 0 <= now - identity.received_ns <= self.stale_ns
            and (last is None or (identity.sequence > last.sequence
                                 and int(identity.stamp_ns) >= int(last.stamp_ns)
                                 and identity.received_ns >= last.received_ns)))
        if not valid:
            self.rejected += 1
            return False
        if not self.worker.offer(Input(identity, message, normalize, options, self.generation)):
            return False
        self.last[identity.source_id] = identity
        return True

    def _result(self, sample):
        result = sample.observation
        identity = result.sample.identity
        age = self.clock_ns() - identity.received_ns
        if (result.generation != self.generation or identity != self.last.get(identity.source_id)
                or not 0 <= age <= self.stale_ns):
            self.late_results += 1
            return
        packet = {"schema_version": "robot-scope.scene-packet.v1",
            **identity.packet(), "obstacle_frame": result.obstacle_frame,
            "robot_pose": None, "joint_state": None, "global_path": None,
            "local_trajectory": None, "costmap_snapshot": None, "collision_assessment": None,
            "diagnostics": list(result.sample.diagnostics), "health": self.health(),
            "source_observation": {"source_id": identity.source_id, "kind": result.sample.kind,
                "origin_m": result.sample.origin_m, "frame_id": identity.frame_id,
                "metadata": deepcopy(result.sample.payload.get("metadata", {}))},
            "observation_only": True, "published_to_nav2": False,
            "costmap_ingestion_observed": False, "controller_consumption_observed": False}
        # Sink is a bounded synchronous C1 ingestion port; C3 reads its snapshot.
        self.scene_sink.ingest(deepcopy(packet))
        self.latest_scene = packet

    def health(self):
        now = self.clock_ns()
        sources = {}
        for source in self.source_epochs:
            identity = self.last.get(source)
            age = None if identity is None else now - identity.received_ns
            sources[source] = {"age_ns": age, "stale": age is None or age < 0 or age > self.stale_ns,
                "source_stamp_ns": None if identity is None else identity.stamp_ns,
                "fusion_time": "UNKNOWN" if identity is None or identity.clock_domain == "unknown" else "SOURCE_CLOCK_ONLY"}
        latency = None
        if self.worker and self.worker.latest:
            s = self.worker.latest
            latency = {"queue_ms": (s.processing_started_s-s.enqueued_s)*1000,
                       "processing_ms": (s.completed_s-s.processing_started_s)*1000,
                       "receipt_to_done_ms": s.completed_s*1000-s.frame.identity.received_ns/1e6}
        return {"sources": sources, "rejected": self.rejected, "late_results": self.late_results,
            "dropped": 0 if self.worker is None else self.worker.dropped,
            "invalid": 0 if self.worker is None else self.worker.invalid, "latency": latency,
            "worker_error": None if self.worker is None else self.worker.error,
            "queue_capacity": 1, "executing_capacity": 1}

    async def close(self):
        self.generation += 1
        if self.worker:
            await self.worker.close()
        self.latest_scene = None


class ReadOnlySource:
    """Same pull port for owner-transferred, recorded, or synthetic samples.

    The caller supplies an iterator/factory; no file/device/topic is opened by
    this class. Explicit iteration is the only execution point.
    """
    def __init__(self, factory, *, config=RuntimeConfig()):
        self.factory, self.config = factory, config

    def samples(self):
        if self.config.mode in {"offline", "dry_run"}:
            raise ValueError("EXPLICIT_EXECUTION_MODE_REQUIRED")
        return iter(self.factory())
