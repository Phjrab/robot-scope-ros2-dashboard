import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import yaml

from robot_dashboard.obstacle_runtime_adapter.ros_port import ReviewRosPort
from robot_dashboard.obstacle_runtime_adapter.messages import pointcloud2
from robot_dashboard.obstacle_runtime_adapter.nav2 import launch_parameters, validate_launch_parameters
from robot_dashboard.obstacle_runtime_adapter.command import Binding, CommandGate, MockCommandSink, RawCommand, constraint_from_d3
from .fixtures import identity, cloud

ROOT = Path(__file__).resolve().parents[2]


class PortTests(unittest.TestCase):
    def test_ros_callback_handoff_itself_is_bounded(self):
        callbacks, messages = [], []
        loop = NS(call_soon_threadsafe=callbacks.append)
        runtime = NS(offer_raw=lambda *a, **kw: messages.append(a))
        port = ReviewRosPort(runtime=runtime, owner_loop=loop, identity_provider=lambda *a: identity())
        for n in range(1200):
            port.handoff(n, identity(), pointcloud2)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(port.handoff_dropped, 1199)
        callbacks[0]()
        self.assertEqual(messages[0][0], 1199)
        port.handoff(1201, identity(), pointcloud2)
        port.close()
        callbacks[-1]()
        self.assertEqual(len(messages), 1)
        self.assertFalse(port.handoff(1202, identity(), pointcloud2))

    def test_ros_start_default_off_before_import_or_topic(self):
        port = ReviewRosPort(runtime=object(), owner_loop=object(), identity_provider=object())
        with self.assertRaisesRegex(ValueError, "EXPLICIT_LOCAL_ROS"):
            port.start(input_topics=["/review/lidar_input"])
        self.assertIsNone(port.node)
        with self.assertRaisesRegex(ValueError, "REVIEW_TOPIC"):
            port.start(input_topics=["/lidar/points"])

    def test_d3_port_calls_validator_and_stop_actually_zero(self):
        b = Binding("goal-1",1,"lease-1","epoch-1","map/r1/tf1","clock-1")
        assessment = dict(freshness={"c4_binding": b.__dict__},
            validity_interval={"clock_id":"clock-1","valid_from_ns":100,"valid_until_ns":200},
            path_ref={"command_sequence":1}, sequence=1, severity="STOP_REQUIRED",
            stamp_ns="1000000000", source_epoch="epoch-1")
        calls = []
        c = constraint_from_d3(assessment, validate_assessment=calls.append, binding=b, command_sequence=1)
        self.assertEqual(len(calls),1)
        sink = MockCommandSink()
        result = CommandGate(sink,b).apply(RawCommand(1,b,100,200,(.2,0,0)),c,now_ns=100)
        self.assertEqual(result.velocity,(0.,0.,0.))
        self.assertEqual(sink.current.reason,"STOP_REQUIRED")
        with self.assertRaises(ValueError):
            constraint_from_d3(assessment,validate_assessment=calls.append,binding=b,command_sequence=2)

    def test_scoped_launch_generation_and_endpoint_injection_reject(self):
        base = yaml.safe_load((ROOT/"config/nav2_params_go2_humble.yaml").read_text())
        p = launch_parameters(base,envelope_radius_m=.65,safety_padding_m=.1)
        scoped = p["/robot_scope_review_x"]
        validate_launch_parameters(scoped)
        scoped["local_costmap"]["local_costmap"]["ros__parameters"]["obstacle_layer"]["geometry"]["clearing"] = True
        with self.assertRaises(ValueError):
            validate_launch_parameters(scoped)
        scoped = launch_parameters(base,envelope_radius_m=.65,safety_padding_m=.1)["/robot_scope_review_x"]
        scoped["planner_server"]["ros__parameters"]["odom_topic"] = "/utlidar/robot_odom"
        with self.assertRaisesRegex(ValueError,"PRODUCT_ENDPOINT"):
            validate_launch_parameters(scoped)

    def test_launch_import_is_inert_and_default_off(self):
        path = ROOT/"ros2/robot_scope_obstacle_adapter/launch/review.launch.py"
        spec = importlib.util.spec_from_file_location("review_launch",path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # A minimal injected launch-substitution double proves the early return;
        # no native launch package, process or DDS is needed for this UNIT test.
        substitutions = NS(LaunchConfiguration=lambda name:NS(perform=lambda context:"false"))
        with patch.dict("sys.modules", {"launch":NS(),"launch.substitutions":substitutions}):
            self.assertEqual(module._start(object()),[])
