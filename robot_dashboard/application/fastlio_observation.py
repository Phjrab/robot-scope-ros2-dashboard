"""Dashboard admission and monitoring for one fixed observation-only service."""

from __future__ import annotations

import asyncio
import copy
import os
import uuid
import threading
import time
from typing import Any

from ..observation_service import (
    LIMIT_SECONDS,
    ObservationService,
    ObservationServiceError,
    inputs_ready,
)
from .ownership_readback import ownership_readback, _control, OwnerLockBusy
from .observation_bridge import bridge_admission_error


class ObservationSessionConflict(RuntimeError):
    pass


class FastlioObservationSession:
    def __init__(self, runtime: Any, *, enabled: bool, service=None) -> None:
        self.runtime, self.enabled = runtime, enabled
        self.service = service or ObservationService()
        self._lock = threading.RLock()
        self._io_lock = asyncio.Lock()
        self._task = None
        self._pending: str | None = None
        self._select_inputs = False
        self._handoff_receipts = {}
        self._bridge_context = None
        self._safety_error = None
        self._owner_failure = None
        self._bridge_start_dispatched = False
        self._bridge_start_uncertain = False
        self._bridge_session = None
        self._bridge_stop_accepted = False
        self._closed = False
        self._updated_at = time.monotonic()
        self._status = dict(
            state="CHECKING" if enabled else "UNAVAILABLE",
            active=False,
            busy=enabled,
            session_id=None,
            remaining_s=None,
            reason="상태 확인 중" if enabled else "관측 서비스 설치가 필요합니다.",
        )

    def busy(self) -> bool:
        with self._lock:
            return bool(
                self._status["busy"]
                or self._pending
                or bool(self._bridge_context and self._bridge_context.get("token"))
                or (self.enabled and time.monotonic() - self._updated_at > 6)
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            result = dict(self._status)
            reason = self.bridge_safety_error()
            if reason and result.get('active') and result.get('state') in {'READY', 'WAITING_INPUTS'}:
                result.update(state='INVALIDATED', busy=True, reason=reason)
            if self._bridge_context and self._bridge_context.get('token') and not result.get('active'):
                result.update(busy=True, reason=self._safety_error or (
                    'OBSERVATION_START_PENDING' if self._bridge_start_dispatched
                    and self._bridge_session is None else 'OBSERVATION_STOP_ACCEPTANCE_UNCONFIRMED'
                    if self._bridge_start_dispatched and not self._bridge_stop_accepted
                    else 'CONTROL_BRIDGE_INHIBIT_RELEASE_PENDING'))
            if self.enabled and time.monotonic() - self._updated_at > 6:
                result.update(
                    state="UNKNOWN",
                    busy=True,
                    reason="관측 상태가 오래됐습니다. 새 상태를 기다립니다.",
                )
            if self._pending and result['state'] != 'UNKNOWN':
                result.update(
                    state="STARTING" if self._pending == "start" else "STOPPING",
                    busy=True,
                )
            context = self._bridge_context
            if context and context.get('token'):
                result['bridge_guard'] = dict(mode='active_inhibited',
                    **self._transport().observation_inhibit_status(context['token']))
            elif context:
                result['bridge_guard'] = dict(mode='inactive', source='systemd', state='INACTIVE')
            else:
                result['bridge_guard'] = None
            result.update(
                schema="robot-scope.fastlio-observation-session.v1",
                owner_failure=copy.deepcopy(self._owner_failure),
                limit_s=LIMIT_SECONDS,
                can_start=self.enabled
                and not self._closed
                and not result["busy"]
                and result["state"] in {"STOPPED", "FAILED"},
                can_stop=self.enabled
                and bool(result.get("session_id"))
                and result["active"]
                and self._pending != "stop"
                and result["state"] != "UNKNOWN",
                observation_only=True,
                map_registration_applied=False,
            )
            return result

    def _transport(self):
        return self.runtime.agent._control_transport

    def _latch_safety(self, reason):
        with self._lock:
            self._safety_error = self._safety_error or reason
        return self._safety_error

    def bridge_safety_error(self):
        """In-memory guard used by snapshots, proposal and handoff watchers."""
        context = self._bridge_context
        if self._safety_error:
            return self._safety_error
        if context is None:
            return None
        try:
            if _control(self.runtime.agent, lock_timeout_s=.1)['busy']:
                return self._latch_safety('CONTROL_OWNER_CHANGED_DURING_OBSERVATION')
            if context.get('token'):
                state = self._transport().observation_inhibit_status(context['token'])
                if state['state'] in {'RELEASING', 'RELEASED'} and not self._status.get('active'):
                    return None
                if state['state'] != 'HELD' and self._pending != 'start':
                    return self._latch_safety(state['reason'] or 'CONTROL_BRIDGE_INHIBIT_LOST')
                if state['reason']:
                    return self._latch_safety(state['reason'])
        except Exception as exc:
            # Preserve the first failed fresh read without exposing owner data.
            # Both control locks have been released before taking this lock.
            with self._lock:
                if self._owner_failure is None:
                    self._owner_failure = dict(
                        sampled_monotonic_s=time.monotonic(), busy_components=[],
                        unknown_components=['control'],
                        unknown_reasons={'control': 'OWNER_LOCK_BUSY' if isinstance(exc, OwnerLockBusy)
                                         else 'OWNER_READ_UNAVAILABLE'},
                        control_lock_site=exc.site if isinstance(exc, OwnerLockBusy) else None,
                    )
            return self._latch_safety('CONTROL_OWNER_UNKNOWN_DURING_OBSERVATION')
        return None

    async def _check_bridge_context(self):
        context = self._bridge_context
        if context is None:
            return
        snapshot = await asyncio.to_thread(self.runtime.lifecycle.control_bridge_snapshot)
        bridge = snapshot.get('systemd', {})
        expected = 'active' if context.get('token') else 'inactive'
        if (bridge.get('available') is not True or bridge.get('active_state') != expected
                or (expected == 'active' and (bridge.get('available') is not True
                    or bridge.get('sub_state') != 'running'
                    or bridge.get('invocation_id') != context['invocation_id']))):
            self._latch_safety('CONTROL_BRIDGE_STATE_CHANGED_DURING_OBSERVATION')
        # Native I/O runs in a worker; the bounded ownership copy stays on the
        # event loop under pipeline_coordination_lock. Offloading this copy
        # can turn an event-loop reader's RLock into a false unknown.
        owners = await self._read_observation_owners(allow_proposal=True)
        allowed = {'fastlio_observation', 'legacy_alignment'}
        global_id = (owners.get('components', {}).get('global_observation') or {}).get('active_id')
        proposals = getattr(self.runtime, '_navigation_initialization_proposals', None)
        if proposals is not None and proposals.owns_observation_job(global_id, self._status.get('session_id')):
            allowed.add('global_observation')
        busy = [name for name in owners['busy_components'] if name not in allowed]
        unknown = [name for name in owners['unknown_components'] if name not in allowed]
        if busy or unknown:
            with self._lock:
                if self._owner_failure is None:
                    self._owner_failure = dict(
                        sampled_monotonic_s=owners['sampled_monotonic_s'],
                        busy_components=busy,
                        unknown_components=unknown,
                        unknown_reasons={name: owners['components'][name].get('reason') for name in unknown},
                    )
                    navigation = owners['components'].get('navigation', {})
                    if navigation.get('lock_site'):
                        self._owner_failure['navigation_lock_site'] = navigation['lock_site']
                        self._owner_failure['navigation_reader_frames'] = navigation.get('reader_frames', [])
            self._latch_safety('OBSERVATION_OWNER_CHANGED_OR_UNKNOWN')
        self.bridge_safety_error()

    async def _read_observation_owners(self, *, allow_proposal=False):
        """Finish a fresh ownership read across brief navigation reader contention.

        The caller retains pipeline_coordination_lock. No start is dispatched
        while sampling; an active observation retains its signed motion inhibit.
        Only navigation/control native lock contention is retryable, never observed
        work, missing owners or failed reads. No cached idle result is accepted.
        Yield on the event loop so a worker holding the lock can finish without
        blocking callbacks or moving the ownership copy to a foreign thread.
        """
        deadline = time.monotonic() + 0.1
        while True:
            owners = ownership_readback(self.runtime)
            allowed = {'fastlio_observation', 'legacy_alignment'}
            global_id = (owners.get('components', {}).get('global_observation') or {}).get('active_id')
            proposals = getattr(self.runtime, '_navigation_initialization_proposals', None)
            if (allow_proposal and proposals is not None
                    and proposals.owns_observation_job(global_id, self._status.get('session_id'))):
                allowed.add('global_observation')
            retryable = (
                not any(name not in allowed for name in owners['busy_components'])
                and bool(owners['unknown_components'])
                and set(owners['unknown_components']) <= {'navigation', 'control'}
                and all(owners['components'][name].get('reason') == 'OWNER_LOCK_BUSY'
                        for name in owners['unknown_components'])
            )
            if not retryable or self._safety_error or time.monotonic() >= deadline:
                return owners
            # Do not synchronously wait for the same contended control lock on
            # the event loop. Yield, then sample every owner again. The caller
            # still checks the signed inhibit before admitting/retaining work;
            # an unresolved owner at the deadline remains unknown and blocks.
            if 'control' not in owners['unknown_components'] and self.bridge_safety_error():
                return owners
            await asyncio.sleep(min(0.01, max(0., deadline - time.monotonic())))

    async def _finish_bridge_inhibit(self):
        context = self._bridge_context
        if not context or not context.get('token'):
            return
        # Once start was dispatched, an inactive read alone is not proof of
        # our exact stop: it can follow a lost dispatch response or an external
        # service exit. Keep the hold until our stop was accepted as well.
        if self._bridge_start_dispatched and not self._bridge_stop_accepted:
            return
        token = context['token']
        transport = self._transport()
        bridge = await asyncio.to_thread(self.runtime.lifecycle.control_bridge_snapshot)
        systemd = bridge.get('systemd', {})
        if systemd.get('available') is True and systemd.get('active_state') == 'inactive':
            transport.forget_observation_inhibit_after_bridge_stop(token)
        else:
            transport.release_observation_inhibit(token)
        if transport.observation_inhibit_status(token)['state'] == 'RELEASED':
            self._bridge_context = None

    def reserve_handoff_receipt(self, handoff_id, session_id, started):
        with self._lock:
            current = self.snapshot()
            if (current.get("state") != "READY" or current.get("active") is not True
                    or current.get("session_id") != session_id
                    or current.get("started_monotonic_s") != started):
                raise ValueError("OBSERVATION_SESSION_CHANGED")
            if len(self._handoff_receipts) >= 32:
                self._handoff_receipts.pop(next(iter(self._handoff_receipts)))
            self._handoff_receipts[handoff_id] = {
                "session_id": session_id, "started": started, "state": "NOT_REQUESTED", "nonce": None}

    def handoff_receipt(self, handoff_id):
        with self._lock:
            item = self._handoff_receipts.get(handoff_id)
            return dict(item) if item else {"state": "OUTCOME_UNKNOWN"}

    def handoff_stop_snapshot(self, handoff_id):
        """Fresh read-only stop evidence for an admission holding the pipeline lock.

        The normal monitor cannot acquire that lock during slow Nav2 preflight.
        Never renew its cache or infer inactivity from an old accepted receipt.
        A concurrent monitor update or transition fences this separate read.
        """
        with self._lock:
            cached = self.snapshot()
            receipt = self.handoff_receipt(handoff_id)
            if (cached.get('state') != 'UNKNOWN' or cached.get('active') is not False
                    or receipt.get('state') != 'INACTIVE_CONFIRMED'
                    or cached.get('session_id') not in (None, receipt.get('session_id'))
                    or self._pending or self._bridge_context is not None or self._closed):
                return cached
            updated_at = self._updated_at
        try:
            current = self.service.status()
        except Exception:
            return cached
        with self._lock:
            if (self._updated_at != updated_at or self._pending
                    or self._bridge_context is not None or self._closed
                    or self.handoff_receipt(handoff_id) != receipt):
                return self.snapshot()
            return dict(current)

    def _handoff_record(self, event, *, status=None, session_id=None):
        # Pure bounded memory update: never call services, user callbacks, or await.
        with self._lock:
            for item in self._handoff_receipts.values():
                state = item["state"]
                if event == "dispatch" and state == "NOT_REQUESTED" and item["session_id"] == session_id:
                    item.update(state="DISPATCH_PENDING", nonce=uuid.uuid4().hex, dispatch_monotonic_ns=time.monotonic_ns())
                elif event == "accepted" and state == "DISPATCH_PENDING" and item["session_id"] == session_id:
                    item["state"] = "DISPATCH_ACCEPTED"
                elif event == "error" and state in {"DISPATCH_PENDING", "DISPATCH_ACCEPTED"}:
                    item["state"] = "OUTCOME_UNKNOWN"
                elif event == "status" and state not in {"INACTIVE_CONFIRMED", "OUTCOME_UNKNOWN"}:
                    same = status.get("session_id") in (None, item["session_id"])
                    start = status.get("started_monotonic_s")
                    if (not same or (start not in (None, 0) and start != item["started"])
                            or (status.get("active") is True and start != item["started"])):
                        item["state"] = "OUTCOME_UNKNOWN"
                    elif status.get("state") in {"UNKNOWN", "FAILED", "UNAVAILABLE"}:
                        item["state"] = "OUTCOME_UNKNOWN"
                    elif (state == "DISPATCH_ACCEPTED" and status.get("state") == "STOPPED"
                          and status.get("active") is False and not status.get("job_pending")):
                        item["state"] = "INACTIVE_CONFIRMED"
                    elif state == "NOT_REQUESTED" and status.get("active") is False:
                        item["state"] = "OUTCOME_UNKNOWN"

    def _try_handoff_record(self, *args, **kwargs):
        try:
            self._handoff_record(*args, **kwargs)
        except Exception:
            # A broken optional journal must never block normal observation stop.
            try:
                with self._lock:
                    self._handoff_receipts.clear()
            except Exception:
                pass

    async def _refresh(self) -> dict[str, Any]:
        if not self.enabled:
            return self.snapshot()
        try:
            status = await asyncio.to_thread(self.service.status)
            if self._bridge_context and status.get('active'):
                binding = (status.get('session_id'), status.get('started_monotonic_s'))
                if self._bridge_session is None and not self._bridge_start_uncertain:
                    self._bridge_session = binding
                elif self._bridge_session is not None and binding != self._bridge_session:
                    self._latch_safety('OBSERVATION_SESSION_CHANGED')
            if self._bridge_context and status.get('active'):
                await self._check_bridge_context()
            if self._safety_error:
                self._try_handoff_record("error")
            self._try_handoff_record("status", status=status)
            if self._pending:
                done = (self._pending == "start" and status["active"]) or (
                    self._pending == "stop" and not status["active"]
                )
                settled = not status.get("job_pending") and status["state"] in {
                    "STOPPED",
                    "FAILED",
                    "UNAVAILABLE",
                }
                waiting_activation = (self._pending == 'start'
                    and self._bridge_start_dispatched and self._bridge_session is None
                    and status.get('state') == 'STOPPED')
                if (done or settled) and not waiting_activation:
                    with self._lock:
                        self._pending = None
            if status["state"] == "WAITING_INPUTS":
                if self._select_inputs:
                    try:
                        # A fixed selection only, after ROS discovery. No pose/TF reset.
                        await asyncio.to_thread(
                            self.runtime.agent.set_sources,
                            {
                                "odometry": "/Odometry",
                                "pointcloud": "/cloud_registered",
                            },
                        )
                        self._select_inputs = False
                    except ValueError:
                        pass  # Topics may not have entered the graph yet.
                pose, cloud = await asyncio.gather(
                    asyncio.to_thread(self.runtime.agent.pose_snapshot),
                    asyncio.to_thread(self.runtime.agent.pointcloud_binary_snapshot),
                )
                if inputs_ready(pose, cloud, status["started_monotonic_s"]):
                    status.update(
                        state="READY",
                        reason="입력 준비 완료 · 지도 기준점을 연결하세요.",
                    )
                else:
                    status["reason"] = (
                        "새 FAST-LIO pose·점군 수신을 기다립니다. 입력 소스를 확인하세요."
                    )
            elif not status["active"] and self._pending != "start":
                self._select_inputs = False
            if (not status.get('active') and not status.get('job_pending')
                    and status.get('state') == 'STOPPED' and self._pending != 'start'):
                await self._finish_bridge_inhibit()
            with self._lock:
                self._status = status
                self._updated_at = time.monotonic()
        except Exception:
            if self._bridge_context is not None and self._bridge_start_dispatched:
                self._latch_safety('OBSERVATION_STATUS_UNCONFIRMED')
            self._try_handoff_record("error")
            with self._lock:
                # Retain an observed session identity so cleanup can be retried.
                self._status.update(
                    state="UNKNOWN",
                    busy=True,
                    reason="관측 상태 조회 실패 · 새 실행을 차단합니다.",
                )
        return self.snapshot()

    async def refresh(self) -> dict[str, Any]:
        # Same ordering as start/stop. Ownership readback requires this shared
        # admission boundary; never acquire it after taking the I/O lock.
        async with self.runtime.pipeline_coordination_lock, self._io_lock:
            return await self._refresh()

    async def _start_blockers(self) -> list[str]:
        bridge_snapshot = await asyncio.to_thread(self.runtime.lifecycle.control_bridge_snapshot)
        readback = await self._read_observation_owners()
        allowed = {"fastlio_observation", "legacy_alignment"}
        blockers = [
            name
            for name in readback["busy_components"] + readback["unknown_components"]
            if name not in allowed
        ]
        bridge = bridge_snapshot.get("systemd", {})
        error = bridge_admission_error(self.runtime, bridge)
        if error:
            blockers.append(error.lower())
        return blockers

    async def start(self) -> dict[str, Any]:
        async with self.runtime.pipeline_coordination_lock, self._io_lock:
            state = await self._refresh()
            if not state["can_start"]:
                raise ObservationSessionConflict(
                    "관측기가 이미 실행 중이거나 시작할 수 없는 상태입니다."
                )
            self.runtime.lifecycle.require_idle()
            blockers = await self._start_blockers()
            if blockers:
                raise ObservationSessionConflict(
                    "다른 작업을 먼저 종료하세요: " + ", ".join(blockers)
                )
            with self._lock:
                self._pending = "start"
                self._select_inputs = True
                self._safety_error = None
                self._owner_failure = None
                self._bridge_start_dispatched = False
                self._bridge_start_uncertain = False
                self._bridge_session = None
                self._bridge_stop_accepted = False
            try:
                bridge_snapshot = await asyncio.to_thread(self.runtime.lifecycle.control_bridge_snapshot)
                bridge = bridge_snapshot.get('systemd', {})
                error = bridge_admission_error(self.runtime, bridge)
                if error:
                    raise ObservationSessionConflict(error)
                self._bridge_context = dict(token=None)
                if bridge.get('active_state') == 'active':
                    token = self._transport().begin_observation_inhibit()
                    self._bridge_context = dict(token=token, invocation_id=bridge['invocation_id'])
                    deadline = time.monotonic() + 2.
                    while True:
                        proof = self._transport().observation_inhibit_status(token)
                        if proof['state'] == 'HELD':
                            break
                        if proof['reason'] or time.monotonic() >= deadline:
                            raise ObservationSessionConflict(proof['reason'] or 'CONTROL_BRIDGE_INHIBIT_ACK_TIMEOUT')
                        await asyncio.sleep(.05)
                await self._check_bridge_context()
                if self._safety_error:
                    raise ObservationSessionConflict(self._safety_error)
            except BaseException:
                with self._lock:
                    self._pending = None
                    self._select_inputs = False
                await self._refresh()
                raise
            try:
                self._bridge_start_dispatched = True
                await asyncio.to_thread(self.service.dispatch, "start")
            except BaseException:
                # Retain the exact inhibit across timeout/cancellation. A late
                # invocation is not a successfully admitted fresh observation.
                self._bridge_start_uncertain = True
                self._latch_safety('OBSERVATION_START_OUTCOME_UNKNOWN')
                with self._lock:
                    self._pending = None
                    self._select_inputs = False
                await self._refresh()
                raise
            return await self._refresh()

    async def stop(self, session_id: str) -> dict[str, Any]:
        async with self.runtime.pipeline_coordination_lock, self._io_lock:
            state = await self._refresh()
            if (
                state["state"] in {"UNKNOWN", "STOPPING"}
                or self._pending == "stop"
                or state["session_id"] != session_id
                or not state["active"]
            ):
                raise ObservationSessionConflict(
                    "실행 세대가 바뀌었거나 이미 종료됐습니다. 상태를 새로 확인하세요."
                )
            with self._lock:
                self._pending = "stop"
                self._select_inputs = False
                self._try_handoff_record("dispatch", session_id=session_id)
            try:
                await asyncio.to_thread(self.service.dispatch, "stop")
            except ObservationServiceError:
                self._try_handoff_record("error")
                await self._refresh()
                raise
            except BaseException:
                self._try_handoff_record("error")
                raise
            self._bridge_stop_accepted = True
            self._try_handoff_record("accepted", session_id=session_id)
            return await self._refresh()

    async def start_monitor(self) -> None:
        if not self.enabled or self._task is not None:
            return
        await self.refresh()

        async def monitor():
            while True:
                await asyncio.sleep(1.0)
                await self.refresh()

        self._task = asyncio.create_task(monitor())

    async def close(self) -> None:
        self._closed = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # BindsTo/PartOf and RuntimeMaxSec own service cleanup. No broad kill.


def configure_fastlio_observation(runtime: Any) -> None:
    runtime.fastlio_observation = FastlioObservationSession(
        runtime,
        enabled=os.environ.get("ROBOT_SCOPE_OBSERVATION_RUNTIME_ENABLED", "0") == "1",
    )
    runtime.lifecycle.set_observation_activity(runtime.fastlio_observation.busy)
