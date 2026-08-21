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
        require_lifecycle_idle: Callable[[], None],
        logger: logging.Logger | None = None,
    ) -> None:
        if not callable(navigation_active):
            raise TypeError("navigation_active must be callable")
        if not callable(require_lifecycle_idle):
            raise TypeError("require_lifecycle_idle must be callable")
        self._manager = manager
        self._catalog = catalog
        self._coordination_lock = coordination_lock
        self._navigation_active = navigation_active
        self._require_lifecycle_idle = require_lifecycle_idle
        self._logger = logger or LOGGER
        self._task: asyncio.Task[None] | None = None

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

        return self._manager.snapshot(since_log_seq=since_log_seq)

    def start_mapping(self) -> dict[str, Any]:
        """Start trusted localization for an already-fenced Nav transaction."""

        return self._manager.start_mapping()

    def stop_mapping_if_job_id(
        self,
        job_id: str,
    ) -> tuple[bool, dict[str, Any]]:
        """Compare-and-stop exactly one Nav-owned mapping process group."""

        return self._manager.stop_mapping_if_job_id(job_id)

    async def start(self) -> dict[str, Any]:
        async with self._coordination_lock:
            self._require_lifecycle_idle()
            self._require_navigation_idle(
                "navigation must stop before mapping can start"
            )
            self._require_task_idle("a map save is in progress")
            return await asyncio.to_thread(self._manager.start_mapping)

    async def stop(self) -> dict[str, Any]:
        async with self._coordination_lock:
            self._require_navigation_idle(
                "navigation must stop before the localization pipeline can stop"
            )
            self._require_task_idle("map save must finish before mapping can stop")
            return await asyncio.to_thread(self._manager.stop_mapping)

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

        return await asyncio.to_thread(self._manager.start_preview)

    async def close(self, *, task_timeout: float = 2.0) -> None:
        """Close process ownership, then boundedly settle its async worker."""

        await asyncio.to_thread(self._manager.close)
        task = self._task
        if task is None or task.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=task_timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return

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


__all__ = [
    "MappingCoordinator",
    "MappingCoordinatorConflict",
    "MappingCoordinatorError",
    "MappingCoordinatorUnavailable",
]
