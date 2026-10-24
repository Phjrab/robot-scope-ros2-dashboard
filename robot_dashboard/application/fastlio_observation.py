"""Dashboard admission and monitoring for one fixed observation-only service."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any

from ..observation_service import (
    LIMIT_SECONDS,
    ObservationService,
    ObservationServiceError,
    inputs_ready,
)
from .ownership_readback import ownership_readback


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
                or (self.enabled and time.monotonic() - self._updated_at > 6)
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            result = dict(self._status)
            if self.enabled and time.monotonic() - self._updated_at > 6:
                result.update(
                    state="UNKNOWN",
                    busy=True,
                    reason="관측 상태가 오래됐습니다. 새 상태를 기다립니다.",
                )
            if self._pending:
                result.update(
                    state="STARTING" if self._pending == "start" else "STOPPING",
                    busy=True,
                )
            result.update(
                schema="robot-scope.fastlio-observation-session.v1",
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

    async def _refresh(self) -> dict[str, Any]:
        if not self.enabled:
            return self.snapshot()
        try:
            status = await asyncio.to_thread(self.service.status)
            if self._pending:
                done = (self._pending == "start" and status["active"]) or (
                    self._pending == "stop" and not status["active"]
                )
                settled = not status.get("job_pending") and status["state"] in {
                    "STOPPED",
                    "FAILED",
                    "UNAVAILABLE",
                }
                if done or settled:
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
            with self._lock:
                self._status = status
                self._updated_at = time.monotonic()
        except Exception:
            with self._lock:
                # Retain an observed session identity so cleanup can be retried.
                self._status.update(
                    state="UNKNOWN",
                    busy=True,
                    reason="관측 상태 조회 실패 · 새 실행을 차단합니다.",
                )
        return self.snapshot()

    async def refresh(self) -> dict[str, Any]:
        async with self._io_lock:
            return await self._refresh()

    def _start_blockers(self) -> list[str]:
        readback = ownership_readback(self.runtime)
        allowed = {"fastlio_observation", "legacy_alignment"}
        blockers = [
            name
            for name in readback["busy_components"] + readback["unknown_components"]
            if name not in allowed
        ]
        bridge = self.runtime.lifecycle.control_bridge_snapshot().get("systemd", {})
        if bridge.get("active_state") != "inactive":
            blockers.append("control_bridge_not_inactive")
        return blockers

    async def start(self) -> dict[str, Any]:
        async with self.runtime.pipeline_coordination_lock, self._io_lock:
            state = await self._refresh()
            if not state["can_start"]:
                raise ObservationSessionConflict(
                    "관측기가 이미 실행 중이거나 시작할 수 없는 상태입니다."
                )
            self.runtime.lifecycle.require_idle()
            blockers = await asyncio.to_thread(self._start_blockers)
            if blockers:
                raise ObservationSessionConflict(
                    "다른 작업을 먼저 종료하세요: " + ", ".join(blockers)
                )
            with self._lock:
                self._pending = "start"
                self._select_inputs = True
            try:
                await asyncio.to_thread(self.service.dispatch, "start")
            except ObservationServiceError:
                # No implicit retry: a timed-out request may have been accepted.
                await self._refresh()
                raise
            return await self._refresh()

    async def stop(self, session_id: str) -> dict[str, Any]:
        async with self.runtime.pipeline_coordination_lock, self._io_lock:
            state = await self._refresh()
            if (
                state["state"] == "UNKNOWN"
                or state["session_id"] != session_id
                or not state["active"]
            ):
                raise ObservationSessionConflict(
                    "실행 세대가 바뀌었거나 이미 종료됐습니다. 상태를 새로 확인하세요."
                )
            with self._lock:
                self._pending = "stop"
                self._select_inputs = False
            try:
                await asyncio.to_thread(self.service.dispatch, "stop")
            except ObservationServiceError:
                await self._refresh()
                raise
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
