"""Transport fixtures exercise the real adapter; no ROS graph or motors."""
import asyncio
import sys
import threading
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from robot_dashboard.application.mission_coordinator import MissionConflict, MissionUnavailable
from robot_dashboard.mission_routes.planner import NativePlanner


def pose():
    return {'x':1.,'y':2.,'yaw':0.}


class PlannerTransportTests(unittest.IsolatedAsyncioTestCase):
    def graph(self, *, frame='map', malformed=False, accepted=True, pending=False):
        calls = []
        class Future:
            def __init__(self, value, done=True): self.value, self.ready = value, done
            def done(self): return self.ready
            def result(self): return self.value
        class Context:
            def ok(self): return True
            def shutdown(self): calls.append('shutdown')
        def stamped():
            return NS(header=NS(frame_id='',stamp=None),pose=NS(position=NS(x=0.,y=0.,z=0.),orientation=NS(x=0.,y=0.,z=0.,w=1.)))
        point = stamped()
        point.pose.position.x = float('nan') if malformed else 1.
        path = NS(header=NS(frame_id=frame),poses=[point])
        class Handle:
            def get_result_async(self): return Future(NS(status=4,result=NS(path=path)),done=not pending)
            def cancel_goal_async(self):
                calls.append('cancel_owned_preview')
                return Future(None)
        handle = Handle()
        handle.accepted = accepted
        class Client:
            def __init__(self, node, action, name): calls.append(name)
            def wait_for_server(self, **kw): return True
            def send_goal_async(self, request):
                calls.append(request)
                return Future(handle)
            def destroy(self): calls.append('destroy_client')
        node = NS(get_clock=lambda:NS(now=lambda:NS(to_msg=lambda:None)),destroy_node=lambda:calls.append('destroy_node'))
        def spin(node, future, timeout_sec):
            if not future.done():
                threading.Event().wait(min(.01,timeout_sec))
        modules = {'rclpy':NS(init=lambda **kw:None,create_node=lambda *a,**kw:node,spin_until_future_complete=spin), 'rclpy.action':NS(ActionClient=Client),'rclpy.context':NS(Context=Context), 'nav2_msgs.action':NS(ComputePathToPose=NS(Goal=lambda:NS())), 'geometry_msgs.msg':NS(PoseStamped=stamped)}
        return modules,calls

    async def test_real_adapter_requests_only_fixed_compute_path_action(self):
        modules,calls=self.graph()
        with patch.dict(sys.modules,modules):
            result=await NativePlanner(enabled=True).plan(pose(),pose())
        self.assertEqual(calls[0],'/compute_path_to_pose')
        request=calls[1]
        self.assertEqual(request.planner_id,'GridBased')
        self.assertTrue(request.use_start)
        self.assertEqual(request.start.header.frame_id,'map')
        self.assertEqual(result['frame'],'map')
        self.assertTrue(result['actual_nav2_run'])  # adapter flag; this test is synthetic evidence
        self.assertIn('destroy_node',calls)

    async def test_wrong_frame_nonfinite_and_rejection_fail_closed(self):
        for options in ({'frame':'camera'},{'malformed':True},{'accepted':False}):
            modules,calls=self.graph(**options)
            with patch.dict(sys.modules,modules):
                with self.assertRaises((MissionConflict,ValueError)):
                    await NativePlanner(enabled=True).plan(pose(),pose())
            self.assertIn('shutdown',calls)

    async def test_timeout_cancels_only_own_preview_and_releases_slot(self):
        modules,calls=self.graph(pending=True)
        planner=NativePlanner(enabled=True,timeout_s=.2)
        with patch.dict(sys.modules,modules):
            with self.assertRaisesRegex(MissionUnavailable,'TIMEOUT'):
                await planner.plan(pose(),pose())
        self.assertIn('cancel_owned_preview',calls)
        self.assertFalse(planner._lock.locked())

    async def test_http_cancellation_waits_for_owned_cleanup(self):
        modules,calls=self.graph(pending=True)
        planner=NativePlanner(enabled=True)
        with patch.dict(sys.modules,modules):
            task=asyncio.create_task(planner.plan(pose(),pose()))
            await asyncio.sleep(.03)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertIn('cancel_owned_preview',calls)
        self.assertFalse(planner._lock.locked())
