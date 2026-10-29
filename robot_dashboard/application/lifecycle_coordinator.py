"""Application coordination for fixed dashboard and control-bridge lifecycles.

The process adapters retain ownership of immutable systemd commands, bounded
workers, and dispatch-time preflight rechecks.  This coordinator owns the
cross-subsystem snapshot projection that feeds those adapters and the gate that
prevents new robot work while either local service is transitioning.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Callable, Mapping, Protocol, Sequence

from ..control_bridge_lifecycle import (
    ControlBridgeLifecycleManager,
    collect_control_bridge_lifecycle_blockers,
)
from ..service_lifecycle import (
    ServiceLifecycleManager,
    collect_service_lifecycle_blockers,
)


CONTROL_BRIDGE_STATUS_STALE_S = 0.75

SnapshotProvider = Callable[[], Mapping[str, Any] | None]
FlagProvider = Callable[[], bool | None]


class ServiceLifecyclePort(Protocol):
    def snapshot(self) -> dict[str, Any]: ...

    def is_busy(self) -> bool: ...

    def schedule_restart(self, *, confirmed: bool) -> dict[str, Any]: ...

    def schedule_stop(self, *, confirmed: bool) -> dict[str, Any]: ...

    def close(self) -> None: ...


class ControlBridgeLifecyclePort(Protocol):
    def snapshot(self) -> dict[str, Any]: ...

    def is_busy(self) -> bool: ...

    def schedule_start(self, *, confirmed: bool) -> dict[str, Any]: ...

    def schedule_stop(self, *, confirmed: bool) -> dict[str, Any]: ...

    def close(self) -> None: ...


class LifecycleTransitionBusy(RuntimeError):
    """Raised when new robot work races a local service transition."""

    _MESSAGES = {
        "dashboard": "a dashboard service lifecycle operation is pending",
        "control_bridge": (
            "a control bridge service lifecycle operation is pending"
        ),
        "observation": "관측 FAST-LIO를 먼저 종료하세요.",
    }

    def __init__(self, lifecycle: str) -> None:
        if lifecycle not in self._MESSAGES:
            raise ValueError("unknown lifecycle transition")
        self.lifecycle = lifecycle
        super().__init__(self._MESSAGES[lifecycle])


class LifecycleCoordinator:
    """Own lifecycle managers and their application-level safety providers."""

    def __init__(
        self,
        *,
        control_snapshot_provider: SnapshotProvider,
        navigation_runtime_snapshot_provider: SnapshotProvider,
        navigation_jobs_snapshot_provider: SnapshotProvider,
        mapping_jobs_snapshot_provider: SnapshotProvider,
        mapping_task_active_provider: FlagProvider,
        navigation_start_snapshot_provider: SnapshotProvider,
        dataset_capture_active_provider: FlagProvider,
        service_lifecycle: ServiceLifecyclePort | None = None,
        control_bridge_lifecycle: ControlBridgeLifecyclePort | None = None,
        control_bridge_autostart: bool = True,
    ) -> None:
        self._control_snapshot_provider = control_snapshot_provider
        self._navigation_runtime_snapshot_provider = (
            navigation_runtime_snapshot_provider
        )
        self._navigation_jobs_snapshot_provider = navigation_jobs_snapshot_provider
        self._mapping_jobs_snapshot_provider = mapping_jobs_snapshot_provider
        self._mapping_task_active_provider = mapping_task_active_provider
        self._navigation_start_snapshot_provider = (
            navigation_start_snapshot_provider
        )
        self._dataset_capture_active_provider = dataset_capture_active_provider
        self._service_lifecycle = service_lifecycle
        self._control_bridge_lifecycle = control_bridge_lifecycle
        self._control_bridge_autostart = control_bridge_autostart is True
        self._bridge_autostart_finished = False
        self._bridge_autostart_lock = threading.RLock()
        self._observation_activity: Callable[[], bool] = lambda: False

    def set_observation_activity(self, provider: Callable[[], bool]) -> None:
        self._observation_activity = provider

    def _observation_active(self) -> bool:
        try:
            return self._observation_activity() is not False
        except Exception:
            return True

    @classmethod
    def from_environment(
        cls,
        *,
        control_snapshot_provider: SnapshotProvider,
        navigation_runtime_snapshot_provider: SnapshotProvider,
        navigation_jobs_snapshot_provider: SnapshotProvider,
        mapping_jobs_snapshot_provider: SnapshotProvider,
        mapping_task_active_provider: FlagProvider,
        navigation_start_snapshot_provider: SnapshotProvider,
        dataset_capture_active_provider: FlagProvider,
        environ: Mapping[str, str] | None = None,
    ) -> "LifecycleCoordinator":
        """Build the fixed managers with callbacks bound to one coordinator."""

        values = os.environ if environ is None else environ
        coordinator = cls(
            control_snapshot_provider=control_snapshot_provider,
            navigation_runtime_snapshot_provider=(
                navigation_runtime_snapshot_provider
            ),
            navigation_jobs_snapshot_provider=navigation_jobs_snapshot_provider,
            mapping_jobs_snapshot_provider=mapping_jobs_snapshot_provider,
            mapping_task_active_provider=mapping_task_active_provider,
            navigation_start_snapshot_provider=(
                navigation_start_snapshot_provider
            ),
            dataset_capture_active_provider=dataset_capture_active_provider,
            control_bridge_autostart=str(values.get("ROBOT_SCOPE_CONTROL_BRIDGE_AUTOSTART", "1"))
                .strip().casefold() in {"1", "true", "yes", "on"},
        )
        coordinator._service_lifecycle = (
            ServiceLifecycleManager.from_environment(
                environ,
                blocker_provider=coordinator.service_blockers,
            )
        )
        coordinator._control_bridge_lifecycle = (
            ControlBridgeLifecycleManager.from_environment(
                environ,
                preflight_provider=coordinator.control_bridge_preflight,
                bridge_status_provider=coordinator.signed_control_bridge_status_fresh,
            )
        )
        return coordinator

    @staticmethod
    def _snapshot(provider: SnapshotProvider) -> Mapping[str, Any] | None:
        try:
            value = provider()
        except Exception:
            return None
        return value if isinstance(value, Mapping) else None

    def _mapping_task_active(self) -> bool:
        try:
            return bool(self._mapping_task_active_provider())
        except Exception:
            # A dashboard transition must not race a task whose ownership
            # cannot be established.
            return True

    def _dataset_capture_active(self) -> bool | None:
        try:
            value = self._dataset_capture_active_provider()
        except Exception:
            return None
        return bool(value) if value is not None else None

    def _navigation_start_snapshot(self) -> Mapping[str, Any]:
        value = self._navigation_start_snapshot_provider()
        if not isinstance(value, Mapping):
            raise TypeError("navigation start provider returned a non-mapping")
        return value

    def service_blockers(self) -> list[str]:
        """Collect fail-closed blockers for dashboard restart or stop."""

        blockers = collect_service_lifecycle_blockers(
            control=self._snapshot(self._control_snapshot_provider),
            navigation_runtime=self._snapshot(
                self._navigation_runtime_snapshot_provider
            ),
            navigation_jobs=self._snapshot(
                self._navigation_jobs_snapshot_provider
            ),
            mapping_jobs=self._snapshot(self._mapping_jobs_snapshot_provider),
            mapping_task_active=self._mapping_task_active(),
        )
        if self._observation_active():
            blockers.append("observation_fastlio_active")
        startup = self._navigation_start_snapshot()
        if startup.get("pending") or startup.get("mapping_owned"):
            blockers.append("navigation_start_pending")

        dataset_active = self._dataset_capture_active()
        if dataset_active is True:
            blockers.append("dataset_capture_active")
        elif dataset_active is None:
            blockers.append("dataset_capture_state_unknown")

        bridge = self._control_bridge_lifecycle
        if bridge is None:
            blockers.append("control_bridge_service_lifecycle_status_unavailable")
        else:
            try:
                if bridge.is_busy():
                    blockers.append("control_bridge_service_transition")
            except Exception:
                blockers.append(
                    "control_bridge_service_lifecycle_status_unavailable"
                )
        return list(dict.fromkeys(blockers))

    def control_bridge_preflight(self) -> dict[str, list[str]]:
        """Collect action-specific blockers for the local bridge unit."""

        service = self._service_lifecycle
        if service is None:
            dashboard_lifecycle_busy: bool | None = None
        else:
            try:
                dashboard_lifecycle_busy = bool(service.is_busy())
            except Exception:
                dashboard_lifecycle_busy = None

        blockers = collect_control_bridge_lifecycle_blockers(
            control=self._snapshot(self._control_snapshot_provider),
            navigation_runtime=self._snapshot(
                self._navigation_runtime_snapshot_provider
            ),
            navigation_jobs=self._snapshot(
                self._navigation_jobs_snapshot_provider
            ),
            mapping_jobs=self._snapshot(self._mapping_jobs_snapshot_provider),
            mapping_task_active=self._mapping_task_active(),
            dataset_capture_active=self._dataset_capture_active(),
            dashboard_service_lifecycle_busy=dashboard_lifecycle_busy,
        )
        if self._observation_active():
            # STOP remains available; only new bridge startup is excluded.
            blockers["start"].append("observation_fastlio_active")
        startup = self._navigation_start_snapshot()
        if startup.get("pending") or startup.get("mapping_owned"):
            for action in ("start", "stop"):
                blockers[action].append("navigation_start_pending")
        return {
            action: list(dict.fromkeys(blockers[action]))
            for action in ("start", "stop")
        }

    def signed_control_bridge_status_fresh(self) -> bool | None:
        """Return authenticated bridge freshness using the fixed stale limit."""

        snapshot = self._snapshot(self._control_snapshot_provider)
        if snapshot is None:
            return None
        try:
            bridge = (
                snapshot.get("bridge")
                if isinstance(snapshot.get("bridge"), Mapping)
                else {}
            )
            age_value = bridge.get("status_age_s")
            if bridge.get("authenticated") is not True or age_value is None:
                return False
            age = float(age_value)
            return 0.0 <= age <= CONTROL_BRIDGE_STATUS_STALE_S
        except (TypeError, ValueError):
            return None

    @property
    def service_lifecycle(self) -> ServiceLifecyclePort:
        if self._service_lifecycle is None:
            raise RuntimeError("dashboard service lifecycle is not configured")
        return self._service_lifecycle

    @property
    def control_bridge_lifecycle(self) -> ControlBridgeLifecyclePort:
        if self._control_bridge_lifecycle is None:
            raise RuntimeError("control bridge lifecycle is not configured")
        return self._control_bridge_lifecycle

    def service_snapshot(self) -> dict[str, Any]:
        return self.service_lifecycle.snapshot()

    def schedule_service_restart(self, *, confirmed: bool) -> dict[str, Any]:
        return self.service_lifecycle.schedule_restart(confirmed=confirmed)

    def schedule_service_stop(self, *, confirmed: bool) -> dict[str, Any]:
        return self.service_lifecycle.schedule_stop(confirmed=confirmed)

    def control_bridge_snapshot(self) -> dict[str, Any]:
        return {**self.control_bridge_lifecycle.snapshot(),
                "automatic_start_enabled": self._control_bridge_autostart}

    def schedule_control_bridge_start(
        self, *, confirmed: bool
    ) -> dict[str, Any]:
        with self._bridge_autostart_lock:
            if confirmed:
                self._bridge_autostart_finished = True
            return self.control_bridge_lifecycle.schedule_start(confirmed=confirmed)

    def ensure_control_bridge_started(self) -> dict[str, Any]:
        """Start the fixed bridge when the configured service is inactive.

        This dashboard-owned startup path does not arm control, acquire a
        lease, assert deadman, or publish a motion command. All normal bridge
        preflight and immutable-service checks still run in ``schedule_start``.
        """

        with self._bridge_autostart_lock:
            snapshot = self.control_bridge_snapshot()
            if not self._control_bridge_autostart or self._bridge_autostart_finished:
                return snapshot
            systemd = snapshot.get("systemd") if isinstance(snapshot.get("systemd"), Mapping) else {}
            if systemd.get("active_state") == "active":
                self._bridge_autostart_finished = True
                return snapshot
            if not snapshot.get("can_start"):
                return snapshot
            # Dispatch once. Service failures keep their existing systemd
            # recovery policy; startup must not defeat a deliberate STOP.
            self._bridge_autostart_finished = True
            return self.control_bridge_lifecycle.schedule_start(confirmed=True)

    def cancel_control_bridge_autostart(self) -> None:
        with self._bridge_autostart_lock:
            self._bridge_autostart_finished = True

    def start_control_bridge_autostart(self) -> asyncio.Task:
        """Keep startup orchestration with the lifecycle owner, outside the UI."""
        try:
            self.ensure_control_bridge_started()
        except Exception:
            # Observability stays available when a bridge start is refused.
            logging.getLogger(__name__).exception('Go2 bridge automatic startup failed')
        return asyncio.create_task(self.wait_for_control_bridge_startup())

    async def wait_for_control_bridge_startup(self, *, attempts=30, interval_s=1.0) -> None:
        """Bounded startup-only readiness wait, never an always-rearm loop."""
        for _ in range(attempts):
            if not self._control_bridge_autostart or self._bridge_autostart_finished:
                return
            await asyncio.sleep(interval_s)
            try:
                await asyncio.to_thread(self.ensure_control_bridge_started)
            except Exception:
                logging.getLogger(__name__).exception('Go2 bridge automatic startup failed')
                return
        self.cancel_control_bridge_autostart()

    def schedule_control_bridge_stop(
        self, *, confirmed: bool
    ) -> dict[str, Any]:
        with self._bridge_autostart_lock:
            if confirmed:
                self._bridge_autostart_finished = True
            return self.control_bridge_lifecycle.schedule_stop(confirmed=confirmed)

    def require_idle(self) -> None:
        """Prevent new work while either service transition is active."""

        if self._observation_active():
            raise LifecycleTransitionBusy("observation")
        if self.service_lifecycle.is_busy():
            raise LifecycleTransitionBusy("dashboard")
        if self.control_bridge_lifecycle.is_busy():
            raise LifecycleTransitionBusy("control_bridge")

    def close(self) -> None:
        """Cancel observers only; neither manager dispatches from ``close``."""

        self.cancel_control_bridge_autostart()
        try:
            self.control_bridge_lifecycle.close()
        finally:
            self.service_lifecycle.close()


__all__: Sequence[str] = (
    "CONTROL_BRIDGE_STATUS_STALE_S",
    "LifecycleCoordinator",
    "LifecycleTransitionBusy",
)
