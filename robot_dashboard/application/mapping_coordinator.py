"""Application-level mapping and saved-map operation coordination.

The coordinator owns cross-subsystem interlocks and background asyncio task
ownership.  Trusted command execution remains in :mod:`mapping_jobs`, while
all map filesystem validation and publication remain in :mod:`saved_maps`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..mapping_jobs import MappingJobError, MappingJobManager
from ..saved_maps import SavedMapCatalog, SavedMapError


LOGGER = logging.getLogger(__name__)

PREVIEW_RECOVERY_INITIAL_DELAY_S = 5.0
PREVIEW_RECOVERY_MAX_DELAY_S = 30.0
_PREVIEW_RECOVERY_PIPELINE_IDLE_STATES = frozenset(
    {"idle", "stopped", "failed"}
)
_PREVIEW_RECOVERY_OPERATION_IDLE_STATES = frozenset(
    {"idle", "succeeded", "failed"}
)


def _public_mapping_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Remove process-local identifiers from the browser-facing projection."""

    projected = dict(snapshot)
    for key in ("preview", "pipeline"):
        value = projected.get(key)
        if isinstance(value, Mapping):
            item = dict(value)
            item.pop("pid", None)
            projected[key] = item
    return projected


class MappingCoordinatorError(RuntimeError):
    """Base class for application-level mapping coordination failures."""


class MappingCoordinatorConflict(MappingCoordinatorError):
    """Raised when another autonomy operation owns a required resource."""


class MappingCoordinatorUnavailable(MappingCoordinatorError):
    """Raised when a configured mapping operation cannot be scheduled."""


class MappingCoordinator:
    """Coordinate mapping, saved-map mutations, and their shared interlocks.

    ``coordination_lock`` must be the same single-process lock used by the
    navigation, manual-control, dataset, and lifecycle application paths.
    ``require_lifecycle_idle`` is intentionally not called by :meth:`stop`:
    stopping owned mapping work is a cleanup path and must remain available
    while an unrelated lifecycle transition is pending.
    """

    def __init__(
        self,
        manager: MappingJobManager,
        catalog: SavedMapCatalog,
        *,
        coordination_lock: asyncio.Lock,
        navigation_active: Callable[[], bool],
        control_lease_active: Callable[[], bool],
        dataset_capture_active: Callable[[], bool],
        require_lifecycle_idle: Callable[[], None],
        logger: logging.Logger | None = None,
    ) -> None:
        if not callable(navigation_active):
            raise TypeError("navigation_active must be callable")
        if not callable(control_lease_active):
            raise TypeError("control_lease_active must be callable")
        if not callable(dataset_capture_active):
            raise TypeError("dataset_capture_active must be callable")
        if not callable(require_lifecycle_idle):
            raise TypeError("require_lifecycle_idle must be callable")
        self._manager = manager
        self._catalog = catalog
        self._coordination_lock = coordination_lock
        self._navigation_active = navigation_active
        self._control_lease_active = control_lease_active
        self._dataset_capture_active = dataset_capture_active
        self._require_lifecycle_idle = require_lifecycle_idle
        self._preview_auto_recovery_enabled = (
            getattr(manager, "preview_auto_recovery_enabled", False) is True
        )
        self._logger = logger or LOGGER
        self._task: asyncio.Task[None] | None = None
        self._preview_recovery_task: asyncio.Task[None] | None = None
        self._preview_recovery_inflight: asyncio.Task[dict[str, Any]] | None = None
        self._preview_recovery_stop = asyncio.Event()

    @property
    def coordination_lock(self) -> asyncio.Lock:
        """Expose the exact shared lock for integration identity checks."""

        return self._coordination_lock

    @property
    def task(self) -> asyncio.Task[None] | None:
        """Return the currently retained bounded background operation task."""

        return self._task

    def task_active(self) -> bool:
        """Report task ownership, failing closed if task state is unreadable."""

        task = self._task
        if task is None:
            return False
        try:
            return not task.done()
        except Exception:
            return True

    def activity(self) -> tuple[bool, list[str]]:
        """Return mapping operations and transitions that conflict with Nav.

        A stable running FAST-LIO pipeline is shared localization
        infrastructure.  It is deliberately not reported as a conflict.
        """

        blockers: list[str] = []
        if self.task_active():
            blockers.append("mapping_operation_active")
        snapshot = self._manager.snapshot()
        pipeline = snapshot.get("pipeline")
        operation = snapshot.get("operation")
        pipeline_state = str(
            pipeline.get("state", "idle") if isinstance(pipeline, Mapping) else "idle"
        )
        operation_state = str(
            operation.get("state", "idle") if isinstance(operation, Mapping) else "idle"
        )
        if pipeline_state in {"starting", "stopping"}:
            blockers.append("mapping_transition")
        if operation_state in {"saving", "stopping"}:
            blockers.append("mapping_operation_active")
        unique = list(dict.fromkeys(blockers))
        return bool(unique), unique

    def pipeline_state(self) -> str:
        """Return the normalized shared localization pipeline state."""

        snapshot = self._manager.snapshot()
        pipeline = snapshot.get("pipeline")
        state = str(
            pipeline.get("state", "failed")
            if isinstance(pipeline, Mapping)
            else "failed"
        )
        if state == "stopped":
            return "idle"
        if state in {"idle", "starting", "running", "stopping", "failed"}:
            return state
        return "failed"

    def snapshot(self, *, since_log_seq: int = 0) -> dict[str, Any]:
        """Expose a bounded manager snapshot through the application port."""

        return _public_mapping_snapshot(
            self._manager.snapshot(since_log_seq=since_log_seq)
        )

    def start_mapping(self) -> dict[str, Any]:
        """Start trusted localization for an already-fenced Nav transaction."""

        return _public_mapping_snapshot(self._manager.start_mapping())

    def stop_mapping_if_job_id(
        self,
        job_id: str,
    ) -> tuple[bool, dict[str, Any]]:
        """Compare-and-stop exactly one Nav-owned mapping process group."""

        stopped, snapshot = self._manager.stop_mapping_if_job_id(job_id)
        return stopped, _public_mapping_snapshot(snapshot)

    async def start(self) -> dict[str, Any]:
        async with self._coordination_lock:
            self._require_lifecycle_idle()
            self._require_navigation_idle(
                "navigation must stop before mapping can start"
            )
            self._require_inactive(
                self._control_lease_active,
                "control lease must be released before mapping can start",
            )
            self._require_inactive(
                self._dataset_capture_active,
                "dataset capture must stop before mapping can start",
            )
            self._require_task_idle("a map save is in progress")
            snapshot = await asyncio.to_thread(self._manager.start_mapping)
            return _public_mapping_snapshot(snapshot)

    async def stop(self) -> dict[str, Any]:
        async with self._coordination_lock:
            self._require_navigation_idle(
                "navigation must stop before the localization pipeline can stop"
            )
            self._require_task_idle("map save must finish before mapping can stop")
            snapshot = await asyncio.to_thread(self._manager.stop_mapping)
            return _public_mapping_snapshot(snapshot)

    async def save(self, name: str, *, create_2d: bool) -> dict[str, Any]:
        async with self._coordination_lock:
            self._require_lifecycle_idle()
            self._require_navigation_idle(
                "navigation must stop before a map can be saved"
            )
            self._require_task_idle("another map save is already in progress")
            safe_name = self._manager.validate_map_name(name)
            kind = "pointcloud3d_2d" if create_2d else "pointcloud3d"
            if kind not in self._manager.allowed_save_kinds:
                raise MappingCoordinatorUnavailable(
                    "requested map save recipe is unavailable"
                )
            coroutine = self._run_map_save(safe_name, kind)
            try:
                self._task = asyncio.create_task(
                    coroutine,
                    name=f"map-save-{safe_name}",
                )
            except Exception:
                coroutine.close()
                raise
        return {"accepted": True, "map_name": safe_name, "kind": kind}

    async def convert_pcd_to_2d(
        self,
        map_id: str,
        name: str,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        async with self._coordination_lock:
            self._require_lifecycle_idle()
            self._require_navigation_idle(
                "navigation must stop before converting a map"
            )
            self._require_task_idle(
                "another map operation is already in progress"
            )
            values = dict(parameters)
            validated = self._catalog.validate_pcd_conversion(
                map_id,
                name,
                **values,
            )
            reservation = self._manager.reserve_local_operation("pcd_to_2d", name)
            operation = reservation["operation"]
            job_id = str(operation["job_id"])
            source_revision = str(validated["source"]["revision"])
            coroutine = self._run_saved_pcd_conversion(
                job_id=job_id,
                map_id=map_id,
                name=name,
                expected_revision=source_revision,
                parameters=values,
            )
            try:
                self._task = asyncio.create_task(
                    coroutine,
                    name=f"pcd-to-2d-{job_id}",
                )
            except Exception as exc:
                coroutine.close()
                self._manager.fail_reserved_local_operation(
                    job_id,
                    "map conversion worker could not be scheduled",
                )
                raise MappingCoordinatorUnavailable(
                    "map conversion worker could not be scheduled"
                ) from exc
        return {
            "accepted": True,
            "job_id": job_id,
            "map_name": name,
            "kind": "pcd_to_2d",
            "operation": operation,
            "source": validated["source"],
            "parameters": validated["parameters"],
            "filter": "projected_xy_density",
        }

    async def save_edited_copy(
        self,
        map_id: str,
        name: str,
        source_revision: str,
        runs: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        async with self._coordination_lock:
            self._require_lifecycle_idle()
            self._require_navigation_idle(
                "navigation must stop before editing a map"
            )
            self._require_task_idle("map operation must finish before editing")
            return await asyncio.to_thread(
                self._catalog.save_edited_copy,
                map_id,
                name,
                source_revision,
                list(runs),
            )

    async def update_annotations(
        self,
        map_id: str,
        map_revision: str,
        base_annotation_revision: str,
        points: Sequence[Mapping[str, Any]],
        polygons: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Publish a full annotation document while map mutations are idle."""

        async with self._coordination_lock:
            self._require_lifecycle_idle()
            self._require_navigation_idle(
                "navigation must stop before map annotations can be changed"
            )
            self._require_task_idle(
                "map operation must finish before annotations can be changed"
            )
            return await asyncio.to_thread(
                self._catalog.update_annotations,
                map_id,
                map_revision,
                base_annotation_revision,
                list(points),
                list(polygons),
            )

    async def rename(self, map_id: str, name: str) -> dict[str, Any]:
        async with self._coordination_lock:
            self._require_lifecycle_idle()
            self._require_navigation_idle(
                "navigation must stop before a map can be renamed"
            )
            self._require_task_idle(
                "map save must finish before a map can be renamed"
            )
            return await asyncio.to_thread(self._catalog.rename, map_id, name)

    async def delete(self, map_id: str) -> dict[str, Any]:
        async with self._coordination_lock:
            self._require_lifecycle_idle()
            self._require_navigation_idle(
                "navigation must stop before a map can be deleted"
            )
            self._require_task_idle(
                "map save must finish before a map can be deleted"
            )
            return await asyncio.to_thread(self._catalog.delete, map_id)

    async def start_preview(self) -> dict[str, Any]:
        """Start only the manager's fixed optional observation preview."""

        try:
            snapshot = await asyncio.to_thread(self._manager.start_preview)
        except MappingJobError:
            self._start_preview_auto_recovery_fail_soft()
            raise
        self._start_preview_auto_recovery_fail_soft()
        return _public_mapping_snapshot(snapshot)

    def _start_preview_auto_recovery_fail_soft(self) -> None:
        """Start the optional monitor without failing dashboard startup."""

        try:
            self.start_preview_auto_recovery()
        except Exception:
            self._logger.exception("XT16 preview recovery monitor startup failed")

    def start_preview_auto_recovery(self) -> bool:
        """Own one opt-in monitor for a failed observation-only preview.

        The monitor never starts a mapping pipeline or any autonomy/control
        owner.  Its retry transaction is additionally fenced by the same
        cross-subsystem lock and idle providers used by mapping mutations.
        """

        if not self._preview_auto_recovery_enabled:
            return False
        if self._preview_recovery_stop.is_set():
            return False
        task = self._preview_recovery_task
        if task is not None and not task.done():
            return False
        coroutine = self._run_preview_auto_recovery()
        try:
            self._preview_recovery_task = asyncio.create_task(
                coroutine,
                name="xt16-preview-auto-recovery",
            )
        except Exception:
            coroutine.close()
            raise
        return True

    async def stop_preview_auto_recovery(self) -> None:
        """Stop and settle the single preview recovery monitor.

        This is cooperative instead of cancelling ``to_thread`` work: task
        cancellation cannot stop a worker thread, so waiting here guarantees
        that an in-flight preview transaction finishes before manager cleanup.
        """

        self._preview_recovery_stop.set()
        caller_cancelled = False
        task = self._preview_recovery_task
        if task is not None and not task.done():
            caller_cancelled |= await self._settle_task_uninterruptibly(task)
        if task is not None and task.done() and not task.cancelled():
            # Retrieve any terminal exception before dropping ownership.
            task.exception()
        self._preview_recovery_task = None

        # A task cancelled by an external loop owner cannot cancel work that
        # already entered asyncio.to_thread(). Keep the explicit future until
        # that fixed preview-start transaction has actually returned.
        inflight = self._preview_recovery_inflight
        if inflight is not None and not inflight.done():
            try:
                caller_cancelled |= await self._settle_task_uninterruptibly(
                    inflight
                )
            except Exception:
                self._logger.exception(
                    "XT16 preview start settlement failed during shutdown"
                )
        if inflight is not None and inflight.done() and not inflight.cancelled():
            inflight.exception()
        self._preview_recovery_inflight = None
        if caller_cancelled:
            raise asyncio.CancelledError

    async def close(self, *, task_timeout: float = 2.0) -> None:
        """Close process ownership, then boundedly settle its async worker."""

        caller_cancelled = False
        try:
            await self.stop_preview_auto_recovery()
        except asyncio.CancelledError:
            # Preview settlement completed before the cancellation surfaced.
            # Finish manager cleanup, then preserve caller cancellation.
            caller_cancelled = True
        close_coroutine = asyncio.to_thread(self._manager.close)
        try:
            manager_close = asyncio.create_task(
                close_coroutine,
                name="mapping-manager-close",
            )
        except Exception:
            close_coroutine.close()
            raise
        caller_cancelled |= await self._settle_task_uninterruptibly(
            manager_close
        )
        task = self._task
        if task is None or task.done():
            if caller_cancelled:
                raise asyncio.CancelledError
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=task_timeout)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            if not task.cancelled():
                caller_cancelled = True
        if caller_cancelled:
            raise asyncio.CancelledError

    @staticmethod
    async def _settle_task_uninterruptibly(task: asyncio.Task[Any]) -> bool:
        """Wait for owned work while recording, not propagating, caller cancel."""

        caller_cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                if task.cancelled():
                    break
                caller_cancelled = True
        return caller_cancelled

    async def _run_preview_auto_recovery(self) -> None:
        delay = PREVIEW_RECOVERY_INITIAL_DELAY_S
        while not self._preview_recovery_stop.is_set():
            try:
                await asyncio.wait_for(
                    self._preview_recovery_stop.wait(),
                    timeout=delay,
                )
            except asyncio.TimeoutError:
                pass
            if self._preview_recovery_stop.is_set():
                return
            try:
                recovered = await self._recover_failed_preview_if_safe()
            except asyncio.CancelledError:
                raise
            except Exception:
                # State-provider and manager errors fail closed.  Retrying is
                # bounded so an absent robot cannot create a tight loop.
                self._logger.exception("XT16 preview recovery check failed")
                recovered = False
            delay = (
                PREVIEW_RECOVERY_INITIAL_DELAY_S
                if recovered
                else min(delay * 2.0, PREVIEW_RECOVERY_MAX_DELAY_S)
            )

    async def _recover_failed_preview_if_safe(self) -> bool:
        """Retry only a failed preview while every shared owner is idle."""

        async with self._coordination_lock:
            if self._preview_recovery_stop.is_set():
                return False
            snapshot = await asyncio.to_thread(self._manager.snapshot)
            preview = snapshot.get("preview")
            pipeline = snapshot.get("pipeline")
            operation = snapshot.get("operation")
            if not all(
                isinstance(item, Mapping)
                for item in (preview, pipeline, operation)
            ):
                return False
            if str(preview.get("state", "unknown")) != "failed":
                return False
            if self.task_active():
                return False
            try:
                self._require_lifecycle_idle()
                self._require_navigation_idle(
                    "navigation must stop before preview recovery"
                )
                self._require_inactive(
                    self._control_lease_active,
                    "control lease must be released before preview recovery",
                )
                self._require_inactive(
                    self._dataset_capture_active,
                    "dataset capture must stop before preview recovery",
                )
            except MappingCoordinatorConflict:
                return False
            except Exception:
                # Lifecycle state is unreadable or transitioning.
                return False
            if str(pipeline.get("state", "unknown")) not in (
                _PREVIEW_RECOVERY_PIPELINE_IDLE_STATES
            ):
                return False
            if str(operation.get("state", "unknown")) not in (
                _PREVIEW_RECOVERY_OPERATION_IDLE_STATES
            ):
                return False
            if self._preview_recovery_stop.is_set():
                return False
            start_coroutine = asyncio.to_thread(self._manager.start_preview)
            try:
                inflight = asyncio.create_task(
                    start_coroutine,
                    name="xt16-preview-start-transaction",
                )
            except Exception:
                start_coroutine.close()
                raise
            try:
                self._preview_recovery_inflight = inflight
                restarted = await asyncio.shield(inflight)
            except MappingJobError:
                return False
            finally:
                inflight = self._preview_recovery_inflight
                if inflight is not None and inflight.done():
                    self._preview_recovery_inflight = None
            restarted_preview = restarted.get("preview")
            return bool(
                isinstance(restarted_preview, Mapping)
                and restarted_preview.get("state") in {"starting", "running"}
            )

    async def _run_map_save(self, name: str, kind: str) -> None:
        try:
            await asyncio.to_thread(self._manager.save_map, name, kind)
        except MappingJobError:
            # Expected failures are already present in the manager's bounded
            # operation snapshot and remain visible to polling clients.
            return
        except Exception:
            self._logger.exception("unexpected map save failure")

    async def _run_saved_pcd_conversion(
        self,
        *,
        job_id: str,
        map_id: str,
        name: str,
        expected_revision: str,
        parameters: Mapping[str, Any],
    ) -> None:
        def convert() -> dict[str, Any]:
            return self._catalog.convert_pcd_to_2d(
                map_id,
                name,
                expected_revision=expected_revision,
                cancelled=lambda: self._manager.local_operation_cancelled(job_id),
                publication_guard=lambda: self._manager.local_publication_guard(
                    job_id
                ),
                **dict(parameters),
            )

        try:
            await asyncio.to_thread(
                self._manager.run_reserved_local_operation,
                job_id,
                convert,
            )
        except (MappingJobError, SavedMapError):
            # The manager records the bounded operation failure for polling.
            return
        except Exception:
            self._logger.exception("unexpected saved PCD conversion failure")

    def _require_navigation_idle(self, detail: str) -> None:
        try:
            active = bool(self._navigation_active())
        except Exception as exc:
            # Mutations fail closed when navigation ownership cannot be read.
            raise MappingCoordinatorConflict(detail) from exc
        if active:
            raise MappingCoordinatorConflict(detail)

    def _require_task_idle(self, detail: str) -> None:
        if self.task_active():
            raise MappingCoordinatorConflict(detail)

    @staticmethod
    def _require_inactive(provider: Callable[[], bool], detail: str) -> None:
        try:
            active = bool(provider())
        except Exception as exc:
            raise MappingCoordinatorConflict(detail) from exc
        if active:
            raise MappingCoordinatorConflict(detail)


__all__ = [
    "MappingCoordinator",
    "MappingCoordinatorConflict",
    "MappingCoordinatorError",
    "MappingCoordinatorUnavailable",
]
