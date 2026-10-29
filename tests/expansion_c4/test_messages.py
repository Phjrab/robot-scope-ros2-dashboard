from dataclasses import replace
from types import SimpleNamespace as NS
import unittest

from robot_dashboard.obstacle_runtime_adapter import messages as m
from robot_dashboard.obstacle_runtime_adapter.nav2 import observation, ros_pointcloud, geometry_cloud
from .fixtures import identity, cloud, image, camera, pose_message, header


class MessageTests(unittest.TestCase):
    def test_padded_endian_float_layouts_and_roundtrip(self):
        for big in (False, True):
            for double in (False, True):
                with self.subTest(big=big, double=double):
                    message = cloud(big=big, double=double)
                    i = identity(stamp_ns="9007199254740993123")
                    message.header = header(i.stamp_ns)
                    sample = m.pointcloud2(message, i, origin_m=(0, 0, 0))
                    self.assertEqual(sample.payload["xyz_m"], ((1., 2., 3.), (4., 5., 6.)))
                    self.assertEqual(sample.payload["raw_data"], message.data)
                    obs = observation(sample, topic="/review/lidar_points", source_kind="lidar",
                                      now_ns=i.received_ns, receipt_clock_id=i.receipt_clock_id)
                    result = ros_pointcloud(obs, pointcloud_type=lambda: NS(header=header()), field_type=NS)
                    self.assertEqual(m.stamp_ns(result), i.stamp_ns)
                    self.assertEqual(result.data, message.data)
                    self.assertEqual(m.pointcloud2(result, i).payload["xyz_m"], sample.payload["xyz_m"])

    def test_nonfinite_point_preserves_original_layout(self):
        c = cloud(invalid=True)
        s = m.pointcloud2(c, identity())
        self.assertEqual(s.payload["invalid_points"], 1)
        self.assertEqual(s.payload["raw_data"], c.data)
        self.assertEqual(len(s.payload["xyz_m"]), 1)

    def test_malformed_cloud_rejected(self):
        for mutation in (lambda c: setattr(c, "row_step", 1),
                         lambda c: setattr(c.fields[0], "offset", 999),
                         lambda c: setattr(c, "data", c.data[:-1]),
                         lambda c: setattr(c.fields[1], "datatype", 6)):
            c = cloud()
            mutation(c)
            with self.assertRaises(ValueError):
                m.pointcloud2(c, identity())

    def test_header_cannot_be_replaced_by_now(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_HEADER"):
            m.pointcloud2(cloud(), identity(stamp_ns="1000000001"))

    def test_depth_units_endianness_and_invalid_range(self):
        for big in (False, True):
            s = m.depth_image(image(big=big), identity(), depth_scale_m=.001)
            self.assertEqual(s.payload["depth_m"], (None, 1., None))
            self.assertEqual(s.payload["depth_scale_m"], .001)
        s = m.depth_image(image(encoding="32FC1", values=(float("nan"), 1., float("inf"))),
                          identity(), depth_scale_m=1.)
        self.assertEqual(s.payload["depth_m"], (None, 1., None))
        with self.assertRaises(ValueError):
            m.depth_image(image(encoding="32FC1", values=(1.,)), identity(), depth_scale_m=.001)

    def test_actual_alignment_and_wrong_camera(self):
        c = m.camera_info(camera(), identity(), device_id="rs-1", profile_id="color-1", calibration_id="cal-1")
        meta = dict(device_id="rs-1", aligned_to_profile="color-1", calibration_id="cal-1",
                    alignment_verified=True, depth_profile_id="z16-1")
        d = m.depth_image(image(), identity(), depth_scale_m=.001, metadata=meta)
        self.assertEqual(m.alignment_status(c, d), "ALIGNED_METADATA_ATTESTED")
        for field, value in (("device_id", "go2-rgb"), ("aligned_to_profile", "other"),
                             ("calibration_id", None), ("alignment_verified", False)):
            wrong = m.depth_image(image(), identity(), depth_scale_m=.001, metadata=dict(meta, **{field: value}))
            self.assertIn("geometry_unavailable", m.alignment_status(c, wrong))
        for change in ({"clock_domain": "unknown"}, {"tf_epoch": "tf-2"},
                       {"source_epoch": "epoch-2"}, {"stamp_ns": "1000000001"}):
            self.assertIn("geometry_unavailable", m.alignment_status(c, replace(d, identity=identity(**change))))

    def test_color_image_preserves_stride_profile_and_bytes(self):
        message = NS(header=header(), width=2, height=1, step=8, encoding="bgr8",
                     data=b"\x01\x02\x03\x04\x05\x06xx", is_bigendian=False)
        sample = m.color_image(message, identity(), metadata={"device_id":"fixture-rgb", "profile_id":"rgb1"})
        self.assertEqual(sample.payload["raw_data"], message.data)
        self.assertEqual(sample.payload["metadata"]["profile_id"], "rgb1")
        self.assertEqual(sample.payload["step"], 8)

    def test_yolo_only_preserves_native_boxes_and_no_xyz(self):
        message = NS(header=header(), detections=[{"bbox": [0, 0, 12, 12], "class_id": 9, "score": .7}])
        s = m.detections(message, identity(), metadata={"native_shape": [720, 1280], "model_hash": "fixture"})
        self.assertFalse(s.payload["geometry_available"])
        self.assertIn("geometry_unavailable", s.diagnostics)
        self.assertEqual(s.payload["detections"], message.detections)

    def test_pose_tf_and_joints_keep_source_identity(self):
        i = identity()
        p = m.pose(pose_message(), i)
        self.assertEqual(p.payload["position_m"], (0., 0., .2))
        t = NS(header=header(), child_frame_id="base_link", transform=NS(
            translation=NS(x=1, y=2, z=3), rotation=NS(x=0, y=0, z=0, w=1)))
        self.assertEqual(m.pose(t, i, transform=True).payload["child_frame_id"], "base_link")
        j = NS(header=header(), name=["hip"], position=[.2], velocity=[], effort=[])
        self.assertEqual(m.joints(j, i).identity, i)
        j.position.append(.3)
        with self.assertRaises(ValueError):
            m.joints(j, i)

    def test_sensor_origins_and_mark_clear_separation(self):
        i = identity()
        for source, origin, expected in (("lidar", (0, 0, 0), True), ("depth", (0, 0, 0), False),
                                         ("geometry", None, False), ("lidar", (1, 0, 0), False)):
            s = m.pointcloud2(cloud(), i, origin_m=origin)
            o = observation(s, topic="/review/test", source_kind=source, now_ns=i.received_ns,
                            receipt_clock_id=i.receipt_clock_id)
            self.assertEqual(o.clearing, expected)
            self.assertTrue(o.marking)
            self.assertEqual(o.sample.origin_m, origin)
        with self.assertRaises(ValueError):
            observation(s, topic="/review/test", source_kind="lidar", now_ns=i.received_ns+600_000_000,
                        receipt_clock_id=i.receipt_clock_id)
        transformed = replace(s, identity=replace(i, frame_id="odom"), origin_m=(0.,0.,0.))
        self.assertFalse(observation(transformed, topic="/review/test", source_kind="lidar",
            now_ns=i.received_ns, receipt_clock_id=i.receipt_clock_id).clearing)

    def test_full_geometry_retained_unknown_label_not_filter(self):
        g = geometry_cloud([(1, 2, 3), (4, 5, 6), (7, 8, 9)], identity())
        self.assertEqual(len(g.payload["xyz_m"]), 3)
        self.assertIsNone(g.origin_m)
        self.assertIn("MARKING_ONLY_NO_FREE_RAYS", g.diagnostics)

    def test_live_evidence_rejected(self):
        with self.assertRaises(ValueError):
            identity(evidence_kind="LIVE")
