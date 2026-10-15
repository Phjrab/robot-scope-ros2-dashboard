"""SOFTWARE_TEST: transport fixtures exercise the adapter, never a ROS graph."""
import asyncio
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from robot_dashboard.application.mission_coordinator import MissionConflict, MissionUnavailable
from robot_dashboard.mission_routes.planner import NativePlanner


def pose():
    return {"x": 1., "y": 2., "yaw": 0.}


class PlannerTransportTests(unittest.IsolatedAsyncioTestCase):
    def graph(self, *, frame="map", malformed=False, accepted=True, pending=False,
              acceptance_pending=False, terminal_after_cancel=True, owners=None,
              status_owners=None, gid_changes=False, mismatch_goal=False, spin_hook=None,
              point_frame="", quaternion=None, path_count=1, status=4):
        calls = []
        state = NS(acceptance=None, result=None, sent=threading.Event(), cancelled=threading.Event(), requests=[])

        class Future:
            def __init__(self, value, done=True):
                self.value, self.ready = value, done
            def done(self):
                return self.ready
            def result(self):
                return self.value

        class Context:
            def ok(self):
                return True
            def get_domain_id(self):
                return int(os.environ.get("ROS_DOMAIN_ID", "0"))
            def shutdown(self):
                calls.append("shutdown")

        def stamp():
            return NS(sec=7, nanosec=12)

        def stamped():
            return NS(header=NS(frame_id="", stamp=stamp()), pose=NS(
                position=NS(x=0., y=0., z=0.), orientation=NS(x=0., y=0., z=0., w=1.)))

        point = stamped()
        point.header.frame_id = point_frame
        if quaternion is not None:
            point.pose.orientation = NS(**quaternion)
        point.pose.position.x = float("nan") if malformed else 1.
        path = NS(header=NS(frame_id=frame, stamp=stamp()), poses=[point] * path_count)

        class Handle:
            def get_result_async(self):
                if state.result is None:
                    state.result = Future(NS(status=status, result=NS(path=path)), done=not pending)
                return state.result
            def cancel_goal_async(self):
                calls.append("cancel_owned_preview")
                state.cancelled.set()
                if terminal_after_cancel:
                    state.result.value.status = 5
                    state.result.ready = True
                return Future(NS(return_code=0))

        handle = Handle()
        handle.accepted = accepted

        class Client:
            def __init__(self, node, action, name):
                calls.append(name)
            def wait_for_server(self, **kw):
                return True
            def send_goal_async(self, request, *, goal_uuid):
                calls.append(request)
                state.requests.append(request)
                handle.goal_id = NS(uuid=[0] * 16) if mismatch_goal else goal_uuid
                state.acceptance = Future(handle, done=not acceptance_pending)
                state.sent.set()
                return state.acceptance
            def destroy(self):
                calls.append("destroy_client")

        graph_owners = owners if owners is not None else [("planner_server", "/")]
        graph_calls = 0

        def publishers(topic):
            nonlocal graph_calls
            self.assertEqual(topic, "/compute_path_to_pose/_action/status")
            graph_calls += 1
            nodes = status_owners if status_owners is not None else [("planner_server", "/")]
            return [NS(node_name=name, node_namespace=namespace, topic_type="action_msgs/msg/GoalStatusArray",
                       endpoint_gid=[2 if gid_changes and graph_calls > 1 else 1] * 24)
                    for name, namespace in nodes]

        node = NS(get_clock=lambda: NS(now=lambda: NS(to_msg=stamp)),
                  destroy_node=lambda: calls.append("destroy_node"),
                  get_node_names_and_namespaces=lambda: list(graph_owners),
                  get_publishers_info_by_topic=publishers)

        def spin(node, future, timeout_sec, *, executor):
            self.assertIs(executor.context, node.context)
            if spin_hook:
                spin_hook(state)
            if not future.done():
                threading.Event().wait(min(.005, timeout_sec))

        modules = {
            "rclpy": NS(init=lambda **kw: None, create_node=lambda *a, **kw: create_node(kw), spin_until_future_complete=spin),
            "rclpy.action": NS(ActionClient=Client),
            "rclpy.action.graph": NS(get_action_server_names_and_types_by_node=lambda *args: [
                ("/compute_path_to_pose", ["nav2_msgs/action/ComputePathToPose"])]),
            "rclpy.context": NS(Context=Context),
            "rclpy.executors": NS(SingleThreadedExecutor=lambda **kw: NS(context=kw["context"], shutdown=lambda **_: calls.append("shutdown_executor"))),
            "rclpy.utilities": NS(get_rmw_implementation_identifier=lambda: "rmw_cyclonedds_cpp"),
            "nav2_msgs.action": NS(ComputePathToPose=NS(Goal=lambda: NS())),
            "geometry_msgs.msg": NS(PoseStamped=stamped),
            "unique_identifier_msgs.msg": NS(UUID=lambda **kw: NS(**kw)),
        }
        def create_node(kwargs):
            node.context = kwargs.get("context")
            return node
        return modules, calls, state

    async def test_real_adapter_requests_only_fixed_action_and_preserves_evidence(self):
        modules, calls, state = self.graph()
        with patch.dict(sys.modules, modules):
            result = await NativePlanner(enabled=True).plan(pose(), pose())
        self.assertEqual(calls[0], "/compute_path_to_pose")
        request = state.requests[0]
        self.assertEqual(request.planner_id, "GridBased")
        self.assertTrue(request.use_start)
        self.assertEqual(request.start.header.frame_id, "map")
        self.assertEqual(result["request"]["start"], pose())
        self.assertEqual(result["request"]["header"]["stamp"], {"sec": 7, "nanosec": 12})
        self.assertEqual(len(result["goal_id"]), 32)
        self.assertEqual(result["action_server"]["status_gid"], "01" * 24)
        self.assertEqual(result["ros_environment"]["rmw"], "rmw_cyclonedds_cpp")
        self.assertEqual(result["native_path"]["poses"][0]["orientation"], {"x": 0., "y": 0., "z": 0., "w": 1.})
        self.assertTrue(result["actual_nav2_run"])  # adapter output; fixture remains SOFTWARE_TEST
        self.assertNotIn("cancel_owned_preview", calls)  # already terminal
        self.assertIn("destroy_node", calls)

    async def test_disabled_default_never_constructs_ros_transport(self):
        modules, calls, _ = self.graph()
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(MissionUnavailable, "RESOURCE_WINDOW_REQUIRED"):
                await NativePlanner().plan(pose(), pose())
        self.assertEqual(calls, [])

    async def test_wrong_frame_nonfinite_and_rejection_fail_closed(self):
        for options in ({"frame": "camera"}, {"malformed": True}, {"accepted": False},
                        {"point_frame": "camera"}, {"path_count": 0}, {"path_count": 4097},
                        {"quaternion": {"x": 0., "y": 0., "z": 0., "w": 0.}},
                        {"quaternion": {"x": 0., "y": 0., "z": float("nan"), "w": 1.}},
                        {"status": 6}):
            modules, calls, _ = self.graph(**options)
            with patch.dict(sys.modules, modules):
                with self.assertRaises((MissionConflict, ValueError)):
                    await NativePlanner(enabled=True).plan(pose(), pose())
            self.assertIn("shutdown", calls)

    async def test_effective_rmw_mismatch_and_missing_profile_fail_before_request(self):
        modules, _, state = self.graph()
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"RMW_IMPLEMENTATION": "rmw_fastrtps_cpp"}):
            with self.assertRaisesRegex(MissionUnavailable, "RMW_MISMATCH"):
                await NativePlanner(enabled=True).plan(pose(), pose())
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(sys.modules, modules), patch.dict(os.environ, {"CYCLONEDDS_URI": str(Path(folder) / "missing.xml")}):
                with self.assertRaisesRegex(MissionUnavailable, "ROS_PROFILE_UNAVAILABLE"):
                    await NativePlanner(enabled=True).plan(pose(), pose())
        self.assertEqual(state.requests, [])

    async def test_duplicate_wrong_node_and_status_owner_fail_before_request(self):
        for options in ({"owners": [("planner_server", "/")] * 2},
                        {"owners": [("foreign_planner", "/")]},
                        {"status_owners": [("planner_server", "/")] * 2},
                        {"status_owners": [("foreign_planner", "/")]}):
            modules, _, state = self.graph(**options)
            with patch.dict(sys.modules, modules):
                with self.assertRaisesRegex(MissionConflict, "OWNER"):
                    await NativePlanner(enabled=True).plan(pose(), pose())
            self.assertEqual(state.requests, [])

    async def test_server_restart_during_result_is_rejected(self):
        modules, _, _ = self.graph(gid_changes=True)
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(MissionConflict, "SERVER_IDENTITY_CHANGED"):
                await NativePlanner(enabled=True).plan(pose(), pose())

    async def test_graph_disappearance_is_controlled_unavailable_without_submission(self):
        modules, calls, state = self.graph()
        def vanished(*args):
            raise RuntimeError("native graph exception containing private path")
        modules["rclpy.action.graph"].get_action_server_names_and_types_by_node = vanished
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(MissionUnavailable, "PLANNER_GRAPH_PROVENANCE_UNAVAILABLE"):
                await NativePlanner(enabled=True).plan(pose(), pose())
        self.assertEqual(state.requests, [])
        self.assertIn("shutdown_executor", calls)

    async def test_server_identity_is_pinned_across_requests(self):
        first, _, _ = self.graph()
        changed, _, state = self.graph()
        endpoint = changed["rclpy"].create_node()
        endpoint.get_publishers_info_by_topic = lambda _: [NS(node_name="planner_server", node_namespace="/",
            topic_type="action_msgs/msg/GoalStatusArray", endpoint_gid=[3] * 24)]
        planner = NativePlanner(enabled=True)
        with patch.dict(sys.modules, first):
            await planner.plan(pose(), pose())
        with patch.dict(sys.modules, changed):
            with self.assertRaisesRegex(MissionConflict, "SERVER_IDENTITY_CHANGED"):
                await planner.plan(pose(), pose())
        self.assertEqual(state.requests, [])

    async def test_ros_domain_change_and_profile_content_change_fail_closed(self):
        modules, _, state = self.graph()
        planner = NativePlanner(enabled=True)
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"ROS_DOMAIN_ID": "83"}):
            with self.assertRaisesRegex(MissionConflict, "ROS_ENVIRONMENT_CHANGED"):
                await planner.plan(pose(), pose())
        self.assertEqual(state.requests, [])
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / "dds.xml"
            profile.write_text("<old/>")
            with patch.dict(os.environ, {"CYCLONEDDS_URI": str(profile)}), patch.dict(sys.modules, modules):
                planner = NativePlanner(enabled=True)
                profile.write_text("<new/>")
                with self.assertRaisesRegex(MissionConflict, "ROS_ENVIRONMENT_CHANGED"):
                    await planner.plan(pose(), pose())

    async def test_environment_change_during_result_is_rejected(self):
        changed = False
        def change_environment(state):
            nonlocal changed
            if not changed:
                os.environ["ROS_DOMAIN_ID"] = "83"
                state.result.ready = True
                changed = True
        modules, _, _ = self.graph(pending=True, spin_hook=change_environment)
        with patch.dict(os.environ), patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(MissionConflict, "ROS_ENVIRONMENT_CHANGED"):
                await NativePlanner(enabled=True).plan(pose(), pose())

    async def test_timeout_cancels_only_own_preview_and_releases_slot(self):
        modules, calls, _ = self.graph(pending=True)
        planner = NativePlanner(enabled=True, timeout_s=.2)
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(MissionUnavailable, "TIMEOUT"):
                await planner.plan(pose(), pose())
        self.assertIn("cancel_owned_preview", calls)
        self.assertFalse(planner._lock.locked())

    async def test_http_cancellation_waits_for_owned_cleanup(self):
        modules, calls, state = self.graph(pending=True)
        planner = NativePlanner(enabled=True)
        with patch.dict(sys.modules, modules):
            task = asyncio.create_task(planner.plan(pose(), pose()))
            await asyncio.to_thread(state.sent.wait, .5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertIn("cancel_owned_preview", calls)
        self.assertFalse(planner._lock.locked())

    async def test_repeated_http_cancellation_retains_foreground_admission_until_cleanup(self):
        modules, calls, state = self.graph(pending=True, terminal_after_cancel=False)
        planner = NativePlanner(enabled=True)
        with patch.dict(sys.modules, modules):
            task = asyncio.create_task(planner.plan(pose(), pose()))
            await asyncio.to_thread(state.sent.wait, .5)
            task.cancel()
            await asyncio.to_thread(state.cancelled.wait, .5)
            task.cancel()
            await asyncio.sleep(.02)
            self.assertFalse(task.done())
            self.assertTrue(planner.diagnostics()["foreground_busy"])
            self.assertNotIn("destroy_node", calls)
            state.result.value.status = 5
            state.result.ready = True
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertIn("destroy_node", calls)
        self.assertFalse(planner._lock.locked())
        self.assertFalse(planner.diagnostics()["foreground_busy"])

    async def test_concurrent_preview_fails_without_second_request(self):
        modules, _, state = self.graph(pending=True)
        planner = NativePlanner(enabled=True)
        with patch.dict(sys.modules, modules):
            task = asyncio.create_task(planner.plan(pose(), pose()))
            await asyncio.to_thread(state.sent.wait, .5)
            with self.assertRaisesRegex(MissionConflict, "PLANNER_BUSY"):
                await planner.plan(pose(), pose())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(len(state.requests), 1)

    async def test_acceptance_after_timeout_retains_context_until_owned_cancel_completes(self):
        modules, calls, state = self.graph(acceptance_pending=True, pending=True)
        planner = NativePlanner(enabled=True, timeout_s=.2)
        planner.cleanup_timeout_s = .01
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(MissionUnavailable, "TIMEOUT"):
                await planner.plan(pose(), pose())
            self.assertNotIn("destroy_node", calls)
            self.assertTrue(planner._lock.locked())
            with self.assertRaisesRegex(MissionConflict, "CLEANUP_PENDING"):
                await planner.plan(pose(), pose())
            state.acceptance.ready = True
            await asyncio.to_thread(state.cancelled.wait, .5)
            for _ in range(100):
                if not planner._lock.locked():
                    break
                await asyncio.sleep(.005)
        self.assertIn("cancel_owned_preview", calls)
        self.assertIn("destroy_node", calls)
        self.assertFalse(planner._lock.locked())

    async def test_cleanup_budget_expiry_quarantines_without_false_success(self):
        modules, calls, _ = self.graph(pending=True, terminal_after_cancel=False)
        planner = NativePlanner(enabled=True, timeout_s=.2)
        planner.cleanup_timeout_s = .01
        planner.quarantine_cleanup_timeout_s = .02
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(MissionUnavailable, "TIMEOUT"):
                await planner.plan(pose(), pose())
            await asyncio.sleep(.05)
            self.assertEqual(planner.diagnostics()["blocking_reason"], "PLANNER_CLEANUP_UNCERTAIN")
            with self.assertRaisesRegex(MissionConflict, "CLEANUP_PENDING"):
                await planner.plan(pose(), pose())
        self.assertTrue(planner._lock.locked())
        self.assertNotIn("destroy_node", calls)
        self.assertEqual(calls.count("cancel_owned_preview"), 1)

    async def test_foreign_goal_identity_is_never_cancelled(self):
        modules, calls, _ = self.graph(mismatch_goal=True, pending=True)
        planner = NativePlanner(enabled=True)
        planner.quarantine_cleanup_timeout_s = .01
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(MissionConflict, "GOAL_IDENTITY_MISMATCH"):
                await planner.plan(pose(), pose())
            await asyncio.sleep(.02)
        self.assertNotIn("cancel_owned_preview", calls)
        self.assertTrue(planner._lock.locked())
