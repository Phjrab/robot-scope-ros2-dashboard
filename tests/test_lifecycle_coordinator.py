import unittest
from unittest import mock

from robot_dashboard.application.lifecycle_coordinator import (
    LifecycleCoordinator,
    LifecycleTransitionBusy,
)
from robot_dashboard.control_bridge_lifecycle import ControlBridgeLifecycleManager
from robot_dashboard.service_lifecycle import ServiceLifecycleManager


class FakeServiceLifecycle:
    def __init__(self, events=None):
        self.busy = False
        self.raise_busy = False
        self.events = events if events is not None else []

    def snapshot(self):
        self.events.append("service_snapshot")
        return {"service": "dashboard"}

    def is_busy(self):
        if self.raise_busy:
            raise RuntimeError("status unavailable")
        return self.busy

    def schedule_restart(self, *, confirmed):
        self.events.append(("service_restart", confirmed))
        return {"action": "restart", "confirmed": confirmed}

    def schedule_stop(self, *, confirmed):
        self.events.append(("service_stop", confirmed))
        return {"action": "stop", "confirmed": confirmed}

    def close(self):
        self.events.append("service_close")


class FakeControlBridgeLifecycle:
    def __init__(self, events=None):
        self.busy = False
        self.raise_busy = False
        self.active_state = "inactive"
        self.can_start = True
        self.events = events if events is not None else []

    def snapshot(self):
        self.events.append("bridge_snapshot")
        return {
            "service": "bridge",
            "systemd": {"active_state": self.active_state},
            "can_start": self.can_start,
        }

    def is_busy(self):
        if self.raise_busy:
            raise RuntimeError("status unavailable")
        return self.busy

    def schedule_start(self, *, confirmed):
        self.events.append(("bridge_start", confirmed))
        return {"action": "start", "confirmed": confirmed}

    def schedule_stop(self, *, confirmed):
        self.events.append(("bridge_stop", confirmed))
        return {"action": "stop", "confirmed": confirmed}

    def close(self):
        self.events.append("bridge_close")


class LifecycleCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "control": {
                "enabled": True,
                "transport_configured": True,
                "target_supported": True,
                "target_matches_startup": True,
                "control_restart_required": False,
                "lease": {"active": False, "input_source": None},
                "action_guard": {"active": False},
                "bridge": {"authenticated": True, "status_age_s": 0.1},
            },
            "navigation_runtime": {"active": False, "goal": {"state": "idle"}},
            "navigation_jobs": {"pipeline": {"state": "idle"}},
            "mapping_jobs": {
                "pipeline": {"state": "idle"},
                "operation": {"state": "idle"},
            },
            "mapping_task_active": False,
            "navigation_start": {"pending": False, "mapping_owned": False},
            "dataset_active": False,
        }
        self.events = []
        self.service = FakeServiceLifecycle(self.events)
        self.bridge = FakeControlBridgeLifecycle(self.events)
        self.coordinator = self.make_coordinator()

    def make_coordinator(self, **overrides):
        values = {
            "control_snapshot_provider": lambda: self.state["control"],
            "navigation_runtime_snapshot_provider": (
                lambda: self.state["navigation_runtime"]
            ),
            "navigation_jobs_snapshot_provider": (
                lambda: self.state["navigation_jobs"]
            ),
            "mapping_jobs_snapshot_provider": lambda: self.state["mapping_jobs"],
            "mapping_task_active_provider": (
                lambda: self.state["mapping_task_active"]
            ),
            "navigation_start_snapshot_provider": (
                lambda: self.state["navigation_start"]
            ),
            "dataset_capture_active_provider": (
                lambda: self.state["dataset_active"]
            ),
            "service_lifecycle": self.service,
            "control_bridge_lifecycle": self.bridge,
        }
        values.update(overrides)
        return LifecycleCoordinator(**values)

    def test_dashboard_blockers_cover_owned_work_and_unknown_state(self):
        self.state["mapping_jobs"] = {
            "pipeline": {"state": "running"},
            "operation": {"state": "saving"},
        }
        self.state["mapping_task_active"] = True
        self.state["navigation_start"] = {"pending": True, "mapping_owned": True}
        self.state["dataset_active"] = True
        self.bridge.busy = True

        blockers = self.coordinator.service_blockers()

        self.assertIn("mapping_pipeline_active", blockers)
        self.assertEqual(blockers.count("mapping_operation_active"), 1)
        self.assertIn("navigation_start_pending", blockers)
        self.assertIn("dataset_capture_active", blockers)
        self.assertIn("control_bridge_service_transition", blockers)

        self.state["dataset_active"] = None
        self.bridge.raise_busy = True
        blockers = self.coordinator.service_blockers()
        self.assertIn("dataset_capture_state_unknown", blockers)
        self.assertIn(
            "control_bridge_service_lifecycle_status_unavailable", blockers
        )

    def test_snapshot_and_task_provider_failures_are_fail_closed(self):
        def unavailable():
            raise RuntimeError("unavailable")

        coordinator = self.make_coordinator(
            control_snapshot_provider=unavailable,
            navigation_runtime_snapshot_provider=unavailable,
            navigation_jobs_snapshot_provider=unavailable,
            mapping_jobs_snapshot_provider=unavailable,
            mapping_task_active_provider=unavailable,
        )

        blockers = coordinator.service_blockers()

        self.assertIn("control_status_unavailable", blockers)
        self.assertIn("navigation_status_unavailable", blockers)
        self.assertIn("mapping_status_unavailable", blockers)
        self.assertIn("mapping_operation_active", blockers)

    def test_bridge_preflight_remains_action_specific(self):
        self.state["control"].update(
            enabled=False,
            target_supported=False,
            target_matches_startup=False,
        )
        self.state["mapping_jobs"]["pipeline"]["state"] = "running"
        self.state["mapping_task_active"] = True
        self.state["dataset_active"] = True
        self.state["navigation_start"] = {"pending": True, "mapping_owned": True}
        self.service.busy = True

        blockers = self.coordinator.control_bridge_preflight()

        self.assertEqual(set(blockers), {"start", "stop"})
        self.assertIn("control_not_configured", blockers["start"])
        self.assertIn("control_target_incompatible", blockers["start"])
        self.assertNotIn("control_not_configured", blockers["stop"])
        for action in ("start", "stop"):
            self.assertIn("navigation_start_pending", blockers[action])
            self.assertIn("dashboard_service_lifecycle_active", blockers[action])
            self.assertNotIn("mapping_pipeline_active", blockers[action])
            self.assertNotIn("dataset_capture_active", blockers[action])

    def test_motion_and_unknown_dashboard_state_block_both_bridge_actions(self):
        self.state["control"]["lease"] = {
            "active": True,
            "input_source": "keyboard",
        }
        self.service.raise_busy = True

        blockers = self.coordinator.control_bridge_preflight()

        for action in ("start", "stop"):
            self.assertIn("manual_control_active", blockers[action])
            self.assertIn(
                "dashboard_service_lifecycle_status_unavailable",
                blockers[action],
            )

    def test_signed_bridge_freshness_preserves_false_and_unknown(self):
        self.assertIs(self.coordinator.signed_control_bridge_status_fresh(), True)

        self.state["control"]["bridge"]["status_age_s"] = 0.751
        self.assertIs(self.coordinator.signed_control_bridge_status_fresh(), False)

        self.state["control"]["bridge"] = {
            "authenticated": False,
            "status_age_s": 0.1,
        }
        self.assertIs(self.coordinator.signed_control_bridge_status_fresh(), False)

        self.state["control"]["bridge"] = {
            "authenticated": True,
            "status_age_s": "invalid",
        }
        self.assertIsNone(self.coordinator.signed_control_bridge_status_fresh())

        coordinator = self.make_coordinator(
            control_snapshot_provider=lambda: None,
        )
        self.assertIsNone(coordinator.signed_control_bridge_status_fresh())

    def test_public_operations_delegate_without_weakening_confirmation(self):
        self.assertEqual(
            self.coordinator.service_snapshot(), {"service": "dashboard"}
        )
        self.assertEqual(
            self.coordinator.schedule_service_restart(confirmed=True)["action"],
            "restart",
        )
        self.assertEqual(
            self.coordinator.schedule_service_stop(confirmed=False)["confirmed"],
            False,
        )
        self.assertEqual(
            self.coordinator.control_bridge_snapshot()["service"], "bridge"
        )
        self.assertEqual(
            self.coordinator.schedule_control_bridge_start(confirmed=True)["action"],
            "start",
        )
        self.assertEqual(
            self.coordinator.schedule_control_bridge_stop(confirmed=False)["confirmed"],
            False,
        )
        self.assertIn(("service_restart", True), self.events)
        self.assertIn(("service_stop", False), self.events)
        self.assertIn(("bridge_start", True), self.events)
        self.assertIn(("bridge_stop", False), self.events)

    def test_dashboard_start_ensures_only_an_inactive_startable_bridge(self):
        self.assertEqual(
            self.coordinator.ensure_control_bridge_started()["action"],
            "start",
        )
        self.assertIn(("bridge_start", True), self.events)

        self.events.clear()
        self.bridge.active_state = "active"
        snapshot = self.coordinator.ensure_control_bridge_started()
        self.assertEqual(snapshot["systemd"]["active_state"], "active")
        self.assertNotIn(("bridge_start", True), self.events)

        self.events.clear()
        self.bridge.active_state = "inactive"
        self.bridge.can_start = False
        snapshot = self.coordinator.ensure_control_bridge_started()
        self.assertFalse(snapshot["can_start"])
        self.assertNotIn(("bridge_start", True), self.events)

    def test_new_work_gate_reports_the_exact_busy_lifecycle(self):
        self.coordinator.require_idle()

        self.service.busy = True
        with self.assertRaises(LifecycleTransitionBusy) as caught:
            self.coordinator.require_idle()
        self.assertEqual(caught.exception.lifecycle, "dashboard")
        self.assertEqual(
            str(caught.exception),
            "a dashboard service lifecycle operation is pending",
        )

        self.service.busy = False
        self.bridge.busy = True
        with self.assertRaises(LifecycleTransitionBusy) as caught:
            self.coordinator.require_idle()
        self.assertEqual(caught.exception.lifecycle, "control_bridge")

    def test_close_cancels_bridge_observer_before_dashboard_dispatch(self):
        self.coordinator.close()
        self.assertEqual(self.events, ["bridge_close", "service_close"])

    def test_from_environment_binds_manager_callbacks_to_one_coordinator(self):
        captured = {}
        service = FakeServiceLifecycle()
        bridge = FakeControlBridgeLifecycle()

        def build_service(environ, *, blocker_provider):
            captured["service_environ"] = environ
            captured["blocker_provider"] = blocker_provider
            return service

        def build_bridge(
            environ,
            *,
            preflight_provider,
            bridge_status_provider,
        ):
            captured["bridge_environ"] = environ
            captured["preflight_provider"] = preflight_provider
            captured["bridge_status_provider"] = bridge_status_provider
            return bridge

        environment = {
            "ROBOT_SCOPE_SERVICE_LIFECYCLE_ENABLED": "1",
            "ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_ENABLED": "1",
        }
        with mock.patch.object(
            ServiceLifecycleManager,
            "from_environment",
            side_effect=build_service,
        ), mock.patch.object(
            ControlBridgeLifecycleManager,
            "from_environment",
            side_effect=build_bridge,
        ):
            coordinator = LifecycleCoordinator.from_environment(
                control_snapshot_provider=lambda: self.state["control"],
                navigation_runtime_snapshot_provider=(
                    lambda: self.state["navigation_runtime"]
                ),
                navigation_jobs_snapshot_provider=(
                    lambda: self.state["navigation_jobs"]
                ),
                mapping_jobs_snapshot_provider=(
                    lambda: self.state["mapping_jobs"]
                ),
                mapping_task_active_provider=(
                    lambda: self.state["mapping_task_active"]
                ),
                navigation_start_snapshot_provider=(
                    lambda: self.state["navigation_start"]
                ),
                dataset_capture_active_provider=(
                    lambda: self.state["dataset_active"]
                ),
                environ=environment,
            )

        self.assertIs(coordinator.service_lifecycle, service)
        self.assertIs(coordinator.control_bridge_lifecycle, bridge)
        self.assertIs(captured["service_environ"], environment)
        self.assertIs(captured["bridge_environ"], environment)
        self.assertIs(captured["blocker_provider"].__self__, coordinator)
        self.assertIs(captured["preflight_provider"].__self__, coordinator)
        self.assertIs(captured["bridge_status_provider"].__self__, coordinator)


if __name__ == "__main__":
    unittest.main()
