"""Opt-in owner handoff to the existing one-running/one-pending TrafficWorker.

No subscription, TF lookup, publisher, authority or device is created here.
Only the worker touches Runtime; only the owner loop commits completed bundles.
"""
import asyncio
from copy import deepcopy
from dataclasses import dataclass
import threading
import time

from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig
from robot_dashboard.obstacle_runtime_adapter.messages import pointcloud2
from .sensor import packet_from_pointcloud
from .owner_identity import from_owner


@dataclass(frozen=True)
class Capture:
    transform: dict
    state: dict
    calibration_id: str
    max_range_m: float
    fov_rad: float
    owner_observation: dict


@dataclass(frozen=True)
class Work:
    message: object
    identity: object
    capture: Capture
    context: object
    mapping: object
    origin_m: tuple


@dataclass(frozen=True)
class Completed:
    context: dict  # TrafficWorker's timing protocol, not control authority.
    work: Work
    sample: object
    result: object
    obstacle: dict | None
    error: str | None


class _Pipeline:
    def __init__(self, adapter):
        self.adapter = adapter

    def process(self, work, *, now_s):
        owner, sample, result, obstacle, error = self.adapter, None, None, None, None
        try:
            runtime = owner.runtime
            if runtime.context.key != work.context.key:
                runtime.rebind(work.context, work.mapping)
            sample = pointcloud2(work.message, work.identity, origin_m=work.origin_m)
            packet = packet_from_pointcloud(sample, context=work.context, clock_epoch=work.context.clock_epoch,
                transform=work.capture.transform, calibration_id=work.capture.calibration_id,
                max_range_m=work.capture.max_range_m, fov_rad=work.capture.fov_rad)
            packet.sensor_evidence['lidar']['owner_observation'] = deepcopy(work.capture.owner_observation)
            # Observation-only fixed stationary hypothesis. Never a controller command.
            result = runtime.process(packet, work.capture.state, command_sequence=work.identity.sequence,
                                     velocity=(0., 0., 0.), authority_present=False)
            if not result.sensor_processed or result.assessment is None:
                raise ValueError(result.intent.reason)
            obstacle = runtime.ports.scene_obstacle(result.obstacle_frame)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            error = str(exc)
        return Completed({'processed_s': now_s}, work, sample, result, obstacle, error)


class SceneView:
    """Read-only router-facing facade; C1 still owns every returned wire byte."""
    def __init__(self, owner):
        self.owner = owner

    def snapshot(self):
        with self.owner._scene_lock:
            return self.owner._scene.snapshot()

    @property
    def assets(self):
        return self.owner._scene.assets


class AsyncRuntimeAdapter:
    """All lifecycle/offer calls use one asyncio owner loop; ROS uses handoff.

    capture_provider(identity) is a bounded metadata lookup, returning the exact
    stamped transform/state already supplied by their owners. Message ownership
    transfers until processing ends: the producer must not mutate its data.
    A scene instance belongs exclusively to this adapter (two written slots).
    """
    def __init__(self, runtime, *, capture_provider, scene_factory, config=RuntimeConfig(),
                 source_id, clock_ns=time.monotonic_ns, observation_sink=None):
        if runtime.mode != 'ADVISORY_ONLY':
            raise ValueError('ADVISORY_ONLY_REQUIRED')
        self.runtime, self.capture_provider, self.scene_factory = runtime, capture_provider, scene_factory
        self.config, self.source_id, self.clock_ns = config, source_id, clock_ns
        self.observation_sink = observation_sink
        self.context, self.mapping = runtime.context, runtime.mapping
        self.receipt_clock_id = self.context.host_clock_id
        self._scene_lock = threading.RLock()
        self._scene = self._new_scene(self.context)
        self.scene = SceneView(self)
        self.worker = self.loop = None
        self.closed = False
        self.last = self.latest = self._committed = None
        self.error = 'NO_INPUT'
        self.rejected = self.late_results = self.delivered = 0
        self.publications = 0

    def _new_scene(self, context):
        scene = self.scene_factory(context)
        if (scene.schema_version != '0.2' or scene.map_binding != context.map_binding
                or scene.host_clock_id != context.host_clock_id
                or any(scene.snapshot()[slot] is not None for slot in ('obstacle_frame','collision_assessment','robot_pose','global_path','controller_local_trajectory','costmap_snapshot'))):
            raise ValueError('EXCLUSIVE_EMPTY_C1_V02_SCENE_REQUIRED')
        return scene

    def _owner(self):
        if self.loop is None or asyncio.get_running_loop() is not self.loop or self.closed:
            raise ValueError('ACTIVE_OWNER_LOOP_REQUIRED')

    def start(self):
        if self.config.mode not in {'synthetic','replay','isolated_ros'} or self.worker or self.closed:
            raise ValueError('EXPLICIT_SINGLE_START_REQUIRED')
        from robot_dashboard.competition_traffic.worker import TrafficWorker
        self.loop = asyncio.get_running_loop()
        self.worker = TrafficWorker(_Pipeline(self), clock=lambda: self.clock_ns()/1e9, result_sink=self._result)
        self.worker.start()

    def offer_raw(self, message, identity, normalize=pointcloud2, *, origin_m=(0.,0.,0.)):
        """ReviewRosPort-compatible API; no XYZ normalization on this loop."""
        self._owner()
        try:
            now = self.clock_ns()
            if (normalize is not pointcloud2 or tuple(origin_m or ()) != (0.,0.,0.)
                    or identity.source_id != self.source_id or identity.source_epoch != self.context.source_epoch
                    or identity.binding != (self.context.map_id,self.context.map_revision,self.context.tf_epoch,self.context.map_generation)
                    or identity.receipt_clock_id != self.receipt_clock_id
                    or identity.clock_domain != self.mapping.source_domain
                    or identity.evidence_kind not in {'SYNTHETIC','REPLAY'}
                    or not 0 <= now-identity.received_ns <= self.runtime.ports.limits.max_delay_ns
                    or self.last is not None and (identity.sequence <= self.last.sequence
                        or int(identity.stamp_ns) <= int(self.last.stamp_ns) or identity.received_ns < self.last.received_ns)):
                raise ValueError('OWNER_INPUT_BINDING_OR_ORDER_REJECTED')
            capture = deepcopy(self.capture_provider(identity))
            if not isinstance(capture, Capture):
                raise ValueError('CAPTURE_METADATA_REQUIRED')
            checked = from_owner(message,capture.owner_observation,context=self.context,
                source_id=self.source_id,sequence=identity.sequence,receipt_ns=identity.received_ns,
                clock_domain=identity.clock_domain,evidence_kind=identity.evidence_kind)
            if checked != identity:
                raise ValueError('OWNER_IDENTITY_CHANGED')
            # Bound metadata before retaining it; no point arrays are permitted here.
            from dataclasses import asdict
            self.runtime.ports.contracts.canonical(asdict(capture), 32*1024)
            work = Work(message, identity, capture, self.context, self.mapping, tuple(origin_m))
            if not self.worker.offer(work):
                raise ValueError('WORKER_NOT_ACCEPTING')
            self.last = identity
            return True
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            self.error = str(exc)
            self.rejected += 1
            return False

    def _result(self, sample):
        completed = sample.observation
        work, result = completed.work, completed.result
        now = self.clock_ns()
        if (self.closed or work.context.key != self.context.key
                or not 0 <= now-work.identity.received_ns <= self.runtime.ports.limits.max_delay_ns
                or self._committed and work.identity.sequence <= self._committed[0]['sequence']):
            self.late_results += 1
            return
        try:
            if completed.error:
                raise ValueError(completed.error)
            # Trial the entire transaction using the actual C1 API and same limits.
            # Exclusive ownership makes replay of the last two slots exact. No
            # mutation of C1 private fields, partial frame, or increased budget.
            with self._scene_lock:
                trial = self._new_scene(self.context)
                if self._committed:
                    for slot,value in zip(('obstacle_frame','collision_assessment'),self._committed):
                        if not trial.ingest(slot,value):
                            raise ValueError('C1_TRIAL_PREVIOUS_REJECTED')
                bundle = (completed.obstacle,result.assessment)
                for slot,value in zip(('obstacle_frame','collision_assessment'),bundle):
                    if not trial.ingest(slot,value):
                        raise ValueError('C1_WHOLE_FRAME_REJECTED')
                for slot,value in zip(('obstacle_frame','collision_assessment'),bundle):
                    if not self._scene.ingest(slot,value):
                        raise RuntimeError('EXCLUSIVE_C1_SERVICE_INVARIANT_BROKEN')
                self._committed = deepcopy(bundle)
                self.latest = completed
                self.delivered += 1
                self.error = None
            if self.observation_sink is not None:
                # Publication is after complete actual-core/C1 acceptance. The
                # injected sink may publish original raw marking only, no boxes.
                self.observation_sink(completed)
                self.publications += 1
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            self.error = str(exc)
            self.rejected += 1

    def rebind(self, context, mapping):
        """One fence for map/source/clock/TF changes; every reset advances both.

        Scene invalidation happens immediately. Runtime.rebind occurs in the
        worker before its next current-generation item, never concurrently with
        an old process call. A running old job may finish but cannot commit.
        """
        self._owner()
        if (context.runtime_generation <= self.context.runtime_generation
                or context.map_generation <= self.context.map_generation
                or context.host_clock_id != self.receipt_clock_id
                or context.robot_geometry_hash != self.context.robot_geometry_hash):
            raise ValueError('INCREASING_COMMON_GENERATION_REQUIRED')
        mapping.check(context, mapping.source_domain)
        # Validate the new scene contract before changing the current fence.
        self._new_scene(context)
        with self._scene_lock:
            self._scene.reset(context.map_binding, f'c4-{context.runtime_generation}')
            for slot in ('obstacle_frame','collision_assessment'):
                self._scene.reset_source(slot,context.source_epoch)
            self.context, self.mapping = context, mapping
            self.last = self.latest = self._committed = None
            self.error = 'WAITING_FOR_CURRENT_GENERATION'
        while not self.worker.queue.empty():
            self.worker.queue.get_nowait()
            self.worker.queue.task_done()
            self.worker.dropped += 1

    def health(self):
        age = None if self.last is None else self.clock_ns()-self.last.received_ns
        return dict(mode='ADVISORY_ONLY', severity='UNKNOWN', reason=self.error or (self.worker.error if self.worker else None) or 'OBSERVATION_ONLY',
            generation=self.context.runtime_generation, delivered=self.delivered, rejected=self.rejected,
            late_results=self.late_results, stale=age is None or age<0 or age>self.runtime.ports.limits.max_delay_ns,
            dropped=0 if self.worker is None else self.worker.dropped, executing_capacity=1, pending_capacity=1,
            adapter_publications=self.publications, native_ingestion='NOT_OBSERVED', clearing='NOT_PROVEN',
            product_enforcement_connected=False)

    async def close(self):
        self._owner()
        self.closed = True
        await self.worker.close()
        self.latest = None
