import asyncio
from dataclasses import replace
import threading
import unittest
import json
import os
from pathlib import Path
import subprocess
import tempfile

from experiments.expansion_20261029.c4_runtime.ros_bridge.dependencies import load
from robot_dashboard.obstacle_runtime_adapter.messages import pointcloud2
from robot_dashboard.obstacle_runtime_adapter.ros_port import ReviewRosPort


class ActualAsyncComposition(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = load()
        from . import async_fixtures
        cls.f = async_fixtures

    async def asyncSetUp(self):
        self.adapter,self.packet,self.clock,self.captures,_ = self.f.setup()
        self.adapter.start()

    async def asyncTearDown(self):
        if not self.adapter.closed:
            await self.adapter.close()

    async def settle(self):
        await asyncio.wait_for(self.adapter.worker.queue.join(),5)
        self.assertIsNone(self.adapter.worker.error)

    async def test_actual_chain_metadata_and_whole_bundle(self):
        msg,ident = self.packet()
        self.assertTrue(self.adapter.offer_raw(msg,ident))
        await self.settle()
        snap = self.adapter.scene.snapshot()
        self.assertEqual(self.adapter.delivered,1,self.adapter.health())
        self.assertEqual(snap['schema_version'],'0.2')
        self.assertEqual(snap['obstacle_frame']['stamp_ns'],ident.stamp_ns)
        self.assertEqual(snap['obstacle_frame']['received_monotonic_ns'],str(ident.received_ns))
        self.assertEqual(snap['collision_assessment']['severity'],'UNKNOWN')
        self.assertEqual(self.adapter.latest.sample.payload['raw_data'],msg.data)
        self.assertEqual(self.adapter.runtime.mode,'ADVISORY_ONLY')

    async def test_bounded_worker_one_running_one_latest(self):
        entered,release = threading.Event(),threading.Event()
        actual = self.adapter.runtime.ports.perceive
        calls = []
        def blocked(*args,**kwargs):
            calls.append(threading.get_ident()); entered.set()
            if not release.wait(3): raise RuntimeError('test release deadline')
            return actual(*args,**kwargs)
        self.adapter.runtime.ports.perceive = blocked
        self.adapter.offer_raw(*self.packet(1))
        await asyncio.wait_for(asyncio.to_thread(entered.wait,2),3)
        try:
            for seq in range(2,42): self.assertTrue(self.adapter.offer_raw(*self.packet(seq)))
            self.assertEqual(self.adapter.worker.queue.qsize(),1)
            self.assertEqual(self.adapter.worker.dropped,39)
        finally: release.set()
        await self.settle()
        self.assertEqual(len(calls),2)
        self.assertEqual(len(set(calls)),1)
        self.assertNotEqual(calls[0],threading.get_ident())
        self.assertEqual(self.adapter.scene.snapshot()['obstacle_frame']['sequence'],41)

    async def test_rebind_during_running_discards_old_result_and_pending(self):
        entered,release = threading.Event(),threading.Event()
        actual = self.adapter.runtime.ports.perceive
        def blocked(*args,**kwargs):
            entered.set()
            if not release.wait(3): raise RuntimeError('test release deadline')
            return actual(*args,**kwargs)
        self.adapter.runtime.ports.perceive = blocked
        old = self.packet(1); self.adapter.offer_raw(*old)
        await asyncio.wait_for(asyncio.to_thread(entered.wait,2),3)
        try:
            self.adapter.offer_raw(*self.packet(2))
            context = replace(self.adapter.context,runtime_generation=2,map_generation=1,
                              source_epoch='reconnected',clock_epoch='clock2',tf_epoch='tf2')
            mapping = replace(self.adapter.mapping,source_epoch='reconnected',clock_epoch='clock2')
            self.adapter.rebind(context,mapping)
            self.assertIsNone(self.adapter.scene.snapshot()['obstacle_frame'])
            self.assertFalse(self.adapter.offer_raw(*old))
            self.assertTrue(self.adapter.offer_raw(*self.packet(0)))
        finally: release.set()
        await self.settle()
        self.assertEqual(self.adapter.late_results,1)
        self.assertEqual(self.adapter.runtime.context,context)
        self.assertEqual(self.adapter.scene.snapshot()['obstacle_frame']['source_epoch'],'reconnected')

    async def test_oversized_assessment_does_not_commit_obstacle_half(self):
        self.adapter.offer_raw(*self.packet(1)); await self.settle()
        previous = self.adapter.scene.snapshot()
        actual = self.adapter.runtime.ports.canonical_assessment
        def oversized(*args,**kwargs):
            result = actual(*args,**kwargs)
            result['freshness']['fault_injection'] = 'x'*17000
            return result
        self.adapter.runtime.ports.canonical_assessment = oversized
        self.adapter.offer_raw(*self.packet(2)); await self.settle()
        current = self.adapter.scene.snapshot()
        self.assertEqual(current['obstacle_frame'],previous['obstacle_frame'])
        self.assertEqual(current['collision_assessment'],previous['collision_assessment'])
        self.assertEqual(self.adapter.delivered,1)
        self.assertTrue(self.adapter.error)

    async def test_actual_d2_object_limit_rejects_whole_frame(self):
        points = [(2+i*.5,j*.5,.3) for i in range(8) for j in range(9)]
        self.adapter.offer_raw(*self.packet(points=points)); await self.settle()
        self.assertEqual(self.adapter.error,'GEOMETRY_INCOMPLETE_OBJECT_BUDGET')
        self.assertEqual(self.adapter.delivered,0)
        self.assertIsNone(self.adapter.scene.snapshot()['obstacle_frame'])

    async def test_header_clock_source_and_duplicate_reject(self):
        msg,ident = self.packet()
        self.assertFalse(self.adapter.offer_raw(msg,replace(ident,clock_domain='unknown')))
        self.assertFalse(self.adapter.offer_raw(msg,replace(ident,source_epoch='old')))
        msg.header.stamp.nanosec += 1
        self.assertFalse(self.adapter.offer_raw(msg,ident))
        msg.header.stamp.nanosec -= 1
        self.assertTrue(self.adapter.offer_raw(msg,ident))
        self.assertFalse(self.adapter.offer_raw(msg,ident))
        await self.settle()

    async def test_source_loss_never_refreshes_receipt_or_clears(self):
        self.adapter.offer_raw(*self.packet()); await self.settle()
        self.clock.now += 600_000_000
        self.assertTrue(self.adapter.health()['stale'])
        self.assertIsNone(self.adapter.scene.snapshot()['collision_assessment'])
        self.assertIsNone(self.adapter.scene.snapshot()['obstacle_frame'])
        self.assertEqual(self.adapter.health()['clearing'],'NOT_PROVEN')

    async def test_review_ros_handoff_coalesces_without_subscription(self):
        port = ReviewRosPort(runtime=self.adapter,identity_provider=None,owner_loop=asyncio.get_running_loop())
        for seq in range(1,101): port.handoff(*self.packet(seq),pointcloud2)
        self.assertEqual(port.handoff_dropped,99)
        self.assertIsNone(port.node)
        await asyncio.sleep(0)
        await self.settle()
        self.assertEqual(self.adapter.delivered,1)
        self.assertEqual(self.adapter.scene.snapshot()['obstacle_frame']['sequence'],100)
        port.close()

    async def test_common_generation_fence_required(self):
        ctx = replace(self.adapter.context,runtime_generation=2,source_epoch='restart')
        with self.assertRaisesRegex(ValueError,'INCREASING_COMMON_GENERATION'):
            self.adapter.rebind(ctx,replace(self.adapter.mapping,source_epoch='restart'))

    async def test_actual_tcp_http_to_current_c3(self):
        from experiments.expansion_20261029.c4_runtime.ros_bridge.http_probe import server,fetch
        self.adapter.offer_raw(*self.packet()); await self.settle()
        with server(self.adapter.scene) as url:
            raw = await asyncio.to_thread(fetch,url)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json'; path.write_bytes(raw)
            script=Path(__file__).resolve().parents[2]/'experiments/expansion_20261029/c4_runtime/ros_bridge/consumer_check.mjs'
            checked=subprocess.run([os.environ.get('C4_NODE','node'),str(script),
                str(self.paths['c3']/'robot_dashboard/static/features/obstacle_scene'),str(path)],capture_output=True,text=True,timeout=15)
        self.assertEqual(checked.returncode,0,checked.stderr+checked.stdout)
        self.assertEqual(json.loads(checked.stdout)['status'],'PASS')

    async def test_close_discards_running_result(self):
        entered,release = threading.Event(),threading.Event()
        actual = self.adapter.runtime.ports.perceive
        def blocked(*args,**kwargs):
            entered.set()
            if not release.wait(3): raise RuntimeError('test release deadline')
            return actual(*args,**kwargs)
        self.adapter.runtime.ports.perceive = blocked
        self.adapter.offer_raw(*self.packet())
        await asyncio.wait_for(asyncio.to_thread(entered.wait,2),3)
        await self.adapter.close(); release.set()
        await asyncio.sleep(.05)
        self.assertEqual(self.adapter.delivered,0)
        self.assertIsNone(self.adapter.latest)
