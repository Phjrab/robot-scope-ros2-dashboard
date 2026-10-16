"""SYNTHETIC / UI CONTRACT TEST: these fixtures are not engine evidence."""

from copy import deepcopy
import json
import math
import random
import struct
from types import SimpleNamespace
import unittest

from robot_dashboard.slam_features import (
    FeatureStream, FeatureValidationError, NativeFullSnapshotEvidence, StreamContext,
    parse_pointcloud2, project_map_points, spatial_lod, timestamp_ns,
)


def cloud(points, *, stamp=10_000_000_001, frame="map", endian=False,
          double=False, width=None, padding=0):
    size = 8 if double else 4
    point_step = size * 3 + 4
    width = len(points) if width is None else width
    height = len(points) // width if width else 1
    row_step = width * point_step + padding
    payload = bytearray(row_step * height)
    for i, point in enumerate(points):
        row, col = divmod(i, width)
        struct.pack_into((">" if endian else "<") + ("3d" if double else "3f"),
                         payload, row * row_step + col * point_step, *point)
    return dict(header=dict(stamp=dict(sec=stamp//1_000_000_000,
                                       nanosec=stamp % 1_000_000_000), frame_id=frame),
                width=width, height=height, point_step=point_step, row_step=row_step,
                is_bigendian=endian, fields=[dict(name=name, offset=i*size,
                    datatype=8 if double else 7, count=1) for i, name in enumerate(("x", "y", "z"))],
                data=payload)


class PointCloudContractTests(unittest.TestCase):
    def test_organized_padding_endianness_and_float64(self):
        expected = ((1., 2., 3.), (4., 5., 6.), (-1., -2., -3.), (7., 8., 9.))
        for endian in (False, True):
            for double in (False, True):
                with self.subTest(endian=endian, double=double):
                    parsed = parse_pointcloud2(cloud(expected, endian=endian,
                        double=double, width=2, padding=9))
                    self.assertEqual(parsed.points, expected)
                    self.assertEqual(parsed.source_timestamp_ns, "10000000001")
                    self.assertEqual(parsed.source_count, 4)

    def test_duck_typed_ros_messages(self):
        message = cloud([(1, 2, 3)])
        message["header"] = SimpleNamespace(frame_id="map", stamp=SimpleNamespace(sec=10, nanosec=1))
        message["fields"] = [SimpleNamespace(**field) for field in message["fields"]]
        self.assertEqual(parse_pointcloud2(SimpleNamespace(**message)).points, ((1., 2., 3.),))

    def test_finite_and_range_filter_counts(self):
        parsed = parse_pointcloud2(cloud([(0, 0, 1), (math.nan, 2, 3),
            (math.inf, 0, 0), (1_000_001, 0, 0)]))
        self.assertEqual(parsed.points, ((0., 0., 1.),))
        self.assertEqual(parsed.rejected_nonfinite, 2)
        self.assertEqual(parsed.rejected_range, 1)

    def test_malformed_cloud_is_rejected_before_decoding(self):
        original = cloud([(1, 2, 3), (4, 5, 6)])
        cases = []
        for field, value in (("data", b"bad"), ("row_step", 1), ("point_step", 0),
                             ("is_bigendian", 1), ("width", True), ("height", -1)):
            changed = deepcopy(original)
            changed[field] = value
            cases.append(changed)
        for field, value in (("count", 2), ("datatype", 6), ("offset", 500), ("name", "y")):
            changed = deepcopy(original)
            changed["fields"][0][field] = value
            cases.append(changed)
        overlap = deepcopy(original)
        overlap["fields"][1]["offset"] = 2
        cases.append(overlap)
        for i, invalid in enumerate(cases):
            with self.subTest(case=i):
                with self.assertRaises(FeatureValidationError):
                    parse_pointcloud2(invalid)

    def test_source_count_and_bytes_are_bounded(self):
        with self.assertRaises(FeatureValidationError):
            parse_pointcloud2(cloud([(0, 0, 0)] * 4), max_points=3)
        with self.assertRaises(FeatureValidationError):
            parse_pointcloud2(cloud([(0, 0, 0)]), max_bytes=10)
        truncated = cloud([(0, 0, 1)])
        truncated["data"] += b"extra"
        with self.assertRaisesRegex(FeatureValidationError, "PAYLOAD_LENGTH"):
            parse_pointcloud2(truncated)

    def test_optional_rgb_is_not_a_native_id(self):
        message = cloud([(1, 2, 3)])
        message["fields"].append(dict(name="rgb", offset=12, datatype=6, count=1))
        parsed = parse_pointcloud2(message)
        self.assertFalse(hasattr(parsed, "native_ids"))

    def test_zero_point_frame_is_valid(self):
        self.assertEqual(parse_pointcloud2(cloud([])).points, ())

    def test_nanosecond_stamp_does_not_round_to_javascript_number(self):
        stamp = 1_792_026_000_123_456_789
        parsed = parse_pointcloud2(cloud([(0, 0, 1)], stamp=stamp))
        self.assertEqual(parsed.source_timestamp_ns, str(stamp))
        for invalid in (1.5, True, "1e9", "-1", "１２", 2**64, -1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(FeatureValidationError):
                    timestamp_ns(invalid)


class ProjectionMathTests(unittest.TestCase):
    def project(self, points, **kwargs):
        parameters = dict(position=(0, 0, 0), quaternion_xyzw=(0, 0, 0, 1),
                          intrinsics=(100, 100, 50, 50), width=100, height=100)
        parameters.update(kwargs)
        return project_map_points(points, **parameters)

    def test_identity_translation_and_pixel_boundaries(self):
        pixels, rejected = self.project([(0, 0, 2), (-1, -1, 2), (1, 0, 2),
            (0, 0, -1), (0, 0, 0), (math.nan, 0, 1)])
        self.assertEqual(pixels, [[50, 50], [0, 0]])
        self.assertEqual(rejected, dict(outside_image=1, behind_camera=2, nonfinite=1))
        pixels, _ = self.project([(3, 2, 4)], position=(3, 2, 2))
        self.assertEqual(pixels, [[50, 50]])

    def test_inverse_camera_rotation_uses_map_pose(self):
        q = math.sqrt(0.5)
        pixels, _ = self.project([(2, 0, 0)], quaternion_xyzw=(0, q, 0, q))
        self.assertAlmostEqual(pixels[0][0], 50)
        self.assertAlmostEqual(pixels[0][1], 50)
        pixels, _ = self.project([(0.5, 0, 2)], quaternion_xyzw=(0, 0, q, q))
        self.assertAlmostEqual(pixels[0][0], 50)
        self.assertAlmostEqual(pixels[0][1], 25)

    def test_invalid_quaternion_or_calibration(self):
        for q in ((0, 0, 0, 0), (0, 0, 0, 2), (math.nan, 0, 0, 1)):
            with self.subTest(q=q):
                with self.assertRaises(FeatureValidationError):
                    self.project([], quaternion_xyzw=q)
        with self.assertRaises(FeatureValidationError):
            self.project([], intrinsics=(0, 1, 0, 0))


class FeaturePairingTests(unittest.TestCase):
    def setUp(self):
        self.context = StreamContext("session", 2, "epoch-1")
        self.stream = FeatureStream(self.context)
        self.stamp = 10_000_000_001

    def inputs(self, *, stream=None, image_stamp=None, observation_stamp=None,
               pose_stamp=None, info_stamp=None, points=((0, 0, 2),), revision="cal-1",
               image_sequence=4):
        stream = stream or self.stream
        identity = dict(context=self.context, camera_id="left", width=100, height=100,
                        calibration_revision=revision, frame_id="left_optical")
        stream.record_image(**identity, stamp_ns=self.stamp if image_stamp is None else image_stamp,
                            sequence=image_sequence, received_at=100)
        stream.record_camera_info(**identity, stamp_ns=self.stamp if info_stamp is None else info_stamp,
                                  k=[100, 0, 50, 0, 100, 50, 0, 0, 1])
        stream.record_pose(context=self.context, stamp_ns=self.stamp if pose_stamp is None else pose_stamp,
                           frame_id="map", camera_frame_id="left_optical", position=[0, 0, 0],
                           quaternion_xyzw=[0, 0, 0, 1], received_at=100)
        stream.update_observations(cloud(points, stamp=self.stamp if observation_stamp is None else observation_stamp),
            context=self.context, source_id="/vslam/observations", camera_id="left",
            calibration_revision=revision, provenance="engine_current_observations", received_at=100)
        stream.heartbeat(context=self.context, tracking_state="TRACKING", received_at=100)

    def overlay(self, now=100.1):
        return self.stream.frame(now_monotonic=now)["overlay"]

    def test_exact_pair_keeps_immutable_image_sequence_and_provenance(self):
        self.inputs()
        overlay = self.overlay()
        self.assertEqual(overlay["overlay_kind"], "current_observations_reprojected")
        self.assertEqual(overlay["points"], [[50, 50]])
        self.assertEqual(overlay["image"]["sequence"], 4)
        self.assertEqual(overlay["image"]["source_timestamp_ns"], str(self.stamp))
        self.assertEqual(overlay["source_id"], "/vslam/observations")
        self.assertIsNone(overlay["confidence"])
        self.assertFalse(overlay["native_ids_available"])
        self.assertIsNone(overlay["sensor_to_browser_latency_seconds"])

    def test_tolerance_checks_total_bundle_span(self):
        self.inputs(observation_stamp=self.stamp+10_000_000, pose_stamp=self.stamp-10_000_000)
        self.assertIsNone(self.overlay()["reason"])
        self.stream.reset(self.context)
        self.inputs(observation_stamp=self.stamp+15_000_000, pose_stamp=self.stamp-15_000_000)
        self.assertEqual(self.overlay()["reason"], "NO_VALID_TIME_ALIGNMENT")

    def test_excess_skew_never_pastes_old_points_on_new_image(self):
        self.inputs()
        self.stream.record_image(context=self.context, stamp_ns=self.stamp+21_000_000,
            camera_id="left", width=100, height=100, calibration_revision="cal-1",
            frame_id="left_optical", sequence=5, received_at=100)
        overlay = self.overlay()
        self.assertEqual(overlay["reason"], "NO_VALID_TIME_ALIGNMENT")
        self.assertEqual(overlay["points"], [])
        self.assertEqual(overlay["image"]["sequence"], 5)

    def test_observed_one_frame_native_lag_selects_only_available_exact_pixels(self):
        # Real first-session frame03: native cloud rounds its source to us,
        # while camera/pose keep ns; newest input is 33.297664ms ahead.
        completed = 1_792_119_083_803_611_392
        latest = 1_792_119_083_836_909_056
        observations = 1_792_119_083_803_611_000
        self.inputs(image_stamp=completed, info_stamp=completed, pose_stamp=completed,
                    observation_stamp=observations)
        self.stream.record_image(context=self.context, stamp_ns=latest, camera_id="left", width=100,
            height=100, calibration_revision="cal-1", frame_id="left_optical", sequence=5, received_at=100.1)
        unaligned = self.stream.frame(now_monotonic=100.2)
        self.assertEqual(unaligned["overlay"]["reason"], "NO_VALID_TIME_ALIGNMENT")
        self.assertEqual(unaligned["overlay"]["overlay_skew_ns"], "33298056")
        matched = self.stream.frame(now_monotonic=100.2, image_timestamps_ns=[str(latest), str(completed)])
        self.assertIsNone(matched["overlay"]["reason"])
        self.assertEqual(matched["overlay"]["image"]["source_timestamp_ns"], str(completed))
        self.assertEqual(matched["overlay"]["overlay_skew_ns"], "392")
        self.assertEqual(matched["camera_view"]["image_source_timestamp_ns"], str(completed))
        self.assertEqual(matched["image_selection"]["latest_timestamp_ns"], str(latest))
        self.assertEqual(matched["overlay"]["alignment_source_timestamps_ns"],
            dict(image=str(completed), calibration=str(completed), observations=str(observations), pose=str(completed)))
        # Metadata remaining in the cache never proves old pixels remain.
        absent = self.stream.frame(now_monotonic=100.2, image_timestamps_ns=[latest])
        self.assertEqual(absent["overlay"]["reason"], "NO_VALID_TIME_ALIGNMENT")
        self.assertEqual(absent["image_selection"]["kind"], "latest_input")

    def test_completed_selection_chooses_newest_fresh_bundle_and_clears_on_epoch_reset(self):
        for offset in (0, 33_333_333):
            self.inputs(image_stamp=self.stamp+offset, info_stamp=self.stamp+offset,
                        observation_stamp=self.stamp+offset, pose_stamp=self.stamp+offset)
        matched = self.stream.frame(now_monotonic=100.2,
            image_timestamps_ns=[self.stamp, self.stamp+33_333_333])
        self.assertEqual(matched["image_selection"]["selected_timestamp_ns"], str(self.stamp+33_333_333))
        stale = self.stream.frame(now_monotonic=101.01,
            image_timestamps_ns=[self.stamp, self.stamp+33_333_333])
        self.assertEqual(stale["overlay"]["reason"], "STALE_SOURCE")
        self.assertEqual(stale["image_selection"]["kind"], "latest_input")
        self.stream.reset(StreamContext("next", 3, "new-epoch"))
        reset = self.stream.frame(now_monotonic=100.2, image_timestamps_ns=[self.stamp])
        self.assertEqual(reset["overlay"]["reason"], "WAITING_IMAGE")
        self.assertIsNone(reset["image_selection"]["selected_timestamp_ns"])

    def test_out_of_order_packets_choose_newest_source_image(self):
        self.inputs(image_stamp=self.stamp+5_000_000, info_stamp=self.stamp+5_000_000,
                    observation_stamp=self.stamp+5_000_000, pose_stamp=self.stamp+5_000_000,
                    image_sequence=5)
        self.inputs(image_sequence=4)
        self.assertEqual(self.overlay()["image"]["sequence"], 5)
        self.assertEqual(self.overlay()["overlay_skew_ns"], "0")

    def test_waiting_image_feature_pose_are_distinct(self):
        self.assertEqual(self.overlay()["reason"], "WAITING_IMAGE")
        self.stream.record_image(context=self.context, stamp_ns=self.stamp, camera_id="left",
            width=100, height=100, calibration_revision="cal-1", frame_id="left_optical", received_at=100)
        self.assertEqual(self.overlay()["reason"], "CALIBRATION_UNAVAILABLE")
        self.stream.record_camera_info(context=self.context, stamp_ns=self.stamp, camera_id="left",
            width=100, height=100, calibration_revision="cal-1", frame_id="left_optical",
            k=[100, 0, 50, 0, 100, 50, 0, 0, 1])
        self.assertEqual(self.overlay()["reason"], "OBSERVATIONS_UNAVAILABLE")
        self.stream.update_observations(cloud([]), context=self.context, source_id="observations",
            camera_id="left", calibration_revision="cal-1", provenance="engine", received_at=100)
        self.assertEqual(self.overlay()["reason"], "SLAM_CAMERA_POSE_UNAVAILABLE")

    def test_zero_features_is_supported_empty_output(self):
        self.inputs(points=())
        overlay = self.overlay()
        self.assertIsNone(overlay["reason"])
        self.assertEqual(overlay["overlay_kind"], "current_observations_reprojected")
        self.assertEqual(overlay["points"], [])

    def test_stale_and_lost_hide_previous_features(self):
        self.inputs()
        self.assertEqual(self.overlay(now=101.1)["reason"], "STALE_SOURCE")
        self.stream.heartbeat(context=self.context, tracking_state="LOST", received_at=100.2)
        self.assertEqual(self.overlay()["reason"], "LOST")
        self.stream.heartbeat(context=self.context, tracking_state="TRACKING", received_at=100.3)
        self.assertEqual(self.overlay()["reason"], "OBSERVATIONS_UNAVAILABLE")

    def test_current_observations_are_actual_map_xyz_and_age_independent_of_projection(self):
        self.inputs(points=[(100, 0, -5)])
        frame = self.stream.frame(now_monotonic=100.1)
        self.assertEqual(frame["overlay"]["points"], [])
        self.assertEqual(frame["current_observations"]["points"], [[100, 0, -5]])
        self.assertTrue(frame["current_observations"]["available"])
        self.assertEqual(frame["current_observations"]["coordinate_frame"], "map")
        self.assertEqual(frame["current_observations"]["map_epoch"], "epoch-1")
        self.assertFalse(self.stream.frame(now_monotonic=102)["current_observations"]["available"])
        self.stream.heartbeat(context=self.context, tracking_state="LOST", received_at=100.1)
        self.assertEqual(self.stream.frame(now_monotonic=100.2)["current_observations"]["points"], [])

    def test_calibration_camera_frame_resolution_and_raw_mismatch(self):
        identity = dict(context=self.context, stamp_ns=self.stamp, camera_id="left",
            width=100, height=100, calibration_revision="cal-1", frame_id="left_optical")
        for changed in (dict(camera_id="right"), dict(rectified=False)):
            with self.subTest(changed=changed):
                with self.assertRaises(FeatureValidationError):
                    self.stream.record_image(**(identity | changed))
        for changed in (dict(roi=(1, 0, 90, 100)), dict(binning_x=2), dict(rectified=False),
                        dict(p=[100, 0, 50, -5, 0, 100, 50, 0, 0, 0, 1, 0])):
            with self.subTest(changed=changed):
                with self.assertRaises(FeatureValidationError):
                    self.stream.record_camera_info(**identity, k=[100, 0, 50, 0, 100, 50, 0, 0, 1], **changed)
        self.inputs()
        self.stream.record_image(**(identity | dict(width=200, stamp_ns=self.stamp+1)), received_at=100)
        self.assertEqual(self.overlay()["reason"], "CALIBRATION_UNAVAILABLE")

    def test_pose_cannot_substitute_odometry_or_wrong_optical_frame(self):
        with self.assertRaisesRegex(FeatureValidationError, "POSE_MAP_FRAME_MISMATCH"):
            self.stream.record_pose(context=self.context, stamp_ns=self.stamp,
                frame_id="odom", camera_frame_id="left_optical", position=[0, 0, 0], quaternion_xyzw=[0, 0, 0, 1])
        with self.assertRaisesRegex(FeatureValidationError, "OBSERVATIONS_MAP_FRAME_MISMATCH"):
            self.stream.update_observations(cloud([], frame="odom"), context=self.context,
                source_id="obs", camera_id="left", calibration_revision="cal-1", provenance="engine")

    def test_old_generation_epoch_and_clock_are_fenced(self):
        self.inputs()
        for old in (StreamContext("previous", 2, "epoch-1"), StreamContext("session", 1, "epoch-1"),
                    StreamContext("session", 2, "epoch-0"), StreamContext("session", 2, "epoch-1", "bag")):
            with self.subTest(old=old):
                self.assertFalse(self.stream.update_observations({}, context=old,
                    source_id="obs", camera_id="left", calibration_revision="cal-1", provenance="engine"))
        self.assertEqual(self.stream.frame(now_monotonic=100)["discarded_context_frames"], 4)
        fresh = StreamContext("session", 3, "epoch-2")
        self.stream.reset(fresh)
        self.assertEqual(self.overlay()["reason"], "WAITING_IMAGE")
        self.assertFalse(self.stream.heartbeat(context=self.context, tracking_state="TRACKING"))

    def test_source_clock_reset_requires_explicit_context_reset(self):
        self.inputs()
        with self.assertRaisesRegex(FeatureValidationError, "SOURCE_CLOCK_RESET"):
            self.stream.record_image(context=self.context, stamp_ns=1, camera_id="left", width=100,
                height=100, calibration_revision="cal-1", frame_id="left_optical", received_at=100)
        self.assertEqual(self.overlay()["points"], [])
        self.assertEqual(self.overlay()["reason"], "SOURCE_CLOCK_RESET")
        self.stream.reset(StreamContext("session", 2, "epoch-2"))
        self.assertEqual(self.overlay()["reason"], "WAITING_IMAGE")

    def test_caches_and_overlay_are_bounded(self):
        stream = FeatureStream(self.context, max_observations=7, cache_size=3)
        for i in range(10):
            self.inputs(stream=stream, image_stamp=self.stamp+i, info_stamp=self.stamp+i,
                pose_stamp=self.stamp+i, observation_stamp=self.stamp+i,
                points=[(i/100, 0, 2) for i in range(100)])
        overlay = stream.frame(now_monotonic=100)["overlay"]
        self.assertEqual(overlay["displayed_count"], 7)
        self.assertEqual(overlay["projected_count"], 100)
        self.assertTrue(overlay["decimation"])
        for cache in (stream._images, stream._poses, stream._calibrations, stream._observations):
            self.assertEqual(len(cache), 3)

    def test_camera_view_uses_matched_optical_pose_without_observation_export(self):
        self.inputs()
        self.stream._observations.clear()  # Deliberately absent engine export.
        view = self.stream.camera_view(now_monotonic=100.1)
        self.assertTrue(view["available"])
        self.assertEqual(view["position"], [0, 0, 0])
        self.assertEqual(view["quaternion_xyzw"], [0, 0, 0, 1])
        self.assertEqual(view["intrinsics"], [100, 100, 50, 50])
        self.assertEqual(view["coordinate_frame"], "map")
        self.assertEqual(view["camera_frame_id"], "left_optical")
        self.assertEqual(view["projection_convention"], "rectified_optical_x_right_y_down_z_forward")
        for field in ("source_timestamp_ns", "image_source_timestamp_ns", "pose_source_timestamp_ns",
                      "calibration_source_timestamp_ns"):
            self.assertEqual(view[field], str(self.stamp))
        frame = self.stream.frame(now_monotonic=100.1)
        self.assertEqual(frame["camera_view"], view)
        self.assertEqual(frame["overlay"]["reason"], "OBSERVATIONS_UNAVAILABLE")
        view["position"][0] = 99
        self.assertEqual(self.stream.camera_view(now_monotonic=100.1)["position"], [0, 0, 0])

    def test_camera_view_rejects_mismatched_optical_calibration_and_total_source_skew(self):
        self.inputs(pose_stamp=self.stamp-10_000_000, info_stamp=self.stamp+10_000_000)
        self.assertTrue(self.stream.camera_view(now_monotonic=100.1)["available"])
        self.stream.reset(self.context)
        self.inputs(pose_stamp=self.stamp-15_000_000, info_stamp=self.stamp+15_000_000)
        view = self.stream.camera_view(now_monotonic=100.1)
        self.assertFalse(view["available"])
        self.assertEqual(view["reason"], "NO_VALID_TIME_ALIGNMENT")
        self.stream.reset(self.context)
        self.inputs()
        self.stream._poses.clear()
        self.stream.record_pose(context=self.context, stamp_ns=self.stamp, frame_id="map",
            camera_frame_id="camera_body", position=[0, 0, 0], quaternion_xyzw=[0, 0, 0, 1], received_at=100)
        self.assertEqual(self.stream.camera_view(now_monotonic=100.1)["reason"], "SLAM_CAMERA_POSE_UNAVAILABLE")
        self.stream.record_image(context=self.context, stamp_ns=self.stamp+1, camera_id="left",
            width=100, height=100, calibration_revision="changed-calibration", frame_id="left_optical", received_at=100)
        self.assertEqual(self.stream.camera_view(now_monotonic=100.1)["reason"], "CALIBRATION_UNAVAILABLE")

    def test_camera_view_is_hidden_on_stale_lost_stopped_reset_and_old_context(self):
        self.inputs()
        self.assertEqual(self.stream.camera_view(now_monotonic=101.1)["reason"], "STALE_SOURCE")
        for state in ("LOST", "STOPPED"):
            self.stream.heartbeat(context=self.context, tracking_state=state, received_at=100)
            view = self.stream.camera_view(now_monotonic=100.1)
            self.assertFalse(view["available"])
            self.assertEqual(view["reason"], state)
            self.assertNotIn("position", view)
        self.stream.reset(StreamContext("next-session", 3, "next-epoch"))
        self.assertFalse(self.stream.record_pose(context=self.context, stamp_ns=self.stamp,
            frame_id="map", camera_frame_id="left_optical", position=[0, 0, 0], quaternion_xyzw=[0, 0, 0, 1]))
        view = self.stream.camera_view(now_monotonic=100.1)
        self.assertFalse(view["available"])
        self.assertEqual(view["map_epoch"], "next-epoch")


class GlobalSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.context = StreamContext("session", 3, "epoch")
        self.stream = FeatureStream(self.context, max_global_points=20)

    def replace(self, points, **kwargs):
        options = dict(context=self.context, source_id="/engine/landmarks",
                       provenance="engine_landmark_export", received_at=100)
        options.update(kwargs)
        return self.stream.replace_global(cloud(points), **options)

    def full_evidence(self, count, *, points=None, **kwargs):
        points = [(0, 0, 2)] * count if points is None else points
        fields = dict(export_contract="synthetic_native_full_snapshot_fixture",
            snapshot_id="native-snapshot-1", engine_revision="native-revision-1",
            source_timestamp_ns="10000000001", engine_total_count=count,
            engine_total_source="synthetic_independent_retained_count",
            native_landmark_ids=tuple(range(count)),
            source_cloud_sha256=parse_pointcloud2(cloud(points)).source_cloud_sha256)
        fields.update(kwargs)
        return NativeFullSnapshotEvidence(**fields)

    def test_global_map_includes_points_outside_current_camera_view(self):
        self.replace([(0, 0, 2), (100, 0, -5), (-100, 0, 2)])
        frame = self.stream.frame(now_monotonic=100)
        self.assertEqual(len(frame["global_map"]["points"]), 3)
        self.assertIn([100., 0., -5.], frame["global_map"]["points"])
        self.assertEqual(frame["global_map"]["spatial_scope"], "global_map")
        self.assertEqual(frame["overlay"]["reason"], "WAITING_IMAGE")

    def test_loop_correction_snapshot_replaces_moved_and_deleted_points(self):
        self.replace([(0, 0, 2), (1, 1, 2)])
        first = self.stream.global_snapshot()
        self.replace([(5, 5, 2)])
        corrected = self.stream.global_snapshot()
        self.assertNotEqual(first["snapshot_id"], corrected["snapshot_id"])
        self.assertEqual(corrected["points"], [[5, 5, 2]])
        self.assertEqual(corrected["update_kind"], "replace")
        self.assertIsNone(corrected["engine_revision"])

    def test_backend_limit_unknown_and_subset_counts_are_honest(self):
        self.replace([(0, 0, 2)] * 8, coverage="complete", backend_limit=8)
        snapshot = self.stream.global_snapshot()
        self.assertEqual(snapshot["coverage"], "unknown")
        self.assertIsNone(snapshot["engine_total_count"])
        self.assertEqual(snapshot["exported_count"], 8)
        self.assertEqual(snapshot["backend_limit"], 8)
        self.replace([(0, 0, 2)] * 8, coverage="complete", backend_limit=8, engine_total_count=100)
        self.assertEqual(self.stream.global_snapshot()["coverage"], "subset")
        self.replace([(0, 0, 2)] * 8, coverage="complete", engine_total_count=8)
        snapshot = self.stream.global_snapshot()
        self.assertEqual(snapshot["coverage"], "unknown")
        self.assertEqual(snapshot["coverage_reason"], "FULL_SNAPSHOT_EVIDENCE_UNAVAILABLE")
        self.assertIsNone(snapshot["completeness_evidence"])

    def test_complete_requires_independent_frozen_generation_evidence(self):
        self.replace([(0, 0, 2)] * 8, coverage="complete", engine_total_count=8,
            engine_revision="native-revision-1", full_snapshot_evidence=self.full_evidence(8))
        snapshot = self.stream.global_snapshot()
        self.assertEqual(snapshot["coverage"], "complete")
        self.assertEqual(snapshot["completeness_evidence"]["snapshot_id"], "native-snapshot-1")
        self.assertEqual(snapshot["completeness_evidence"]["unique_native_id_count"], 8)
        self.assertNotIn("native_landmark_ids", snapshot["completeness_evidence"])
        snapshot["completeness_evidence"]["snapshot_id"] = "consumer-mutation"
        self.assertEqual(self.stream.global_snapshot()["completeness_evidence"]["snapshot_id"], "native-snapshot-1")

    def test_filtered_native_export_is_subset_even_with_equal_total_and_proof(self):
        for invalid in ((math.nan, 0, 2), (1_000_001, 0, 2)):
            with self.subTest(invalid=invalid):
                self.replace([(0, 0, 2), invalid], coverage="complete", engine_total_count=2,
                    engine_revision="native-revision-1",
                    full_snapshot_evidence=self.full_evidence(2, points=[(0, 0, 2), invalid]))
                snapshot = self.stream.global_snapshot()
                self.assertEqual(snapshot["coverage"], "subset")
                self.assertEqual(snapshot["coverage_reason"], "SOURCE_POINTS_REJECTED")
                self.assertEqual(snapshot["source_count"], 2)
                self.assertEqual(snapshot["exported_count"], 1)

    def test_inconsistent_full_snapshot_evidence_cannot_replace_previous_map(self):
        self.replace([(1, 0, 2)])
        before = self.stream.global_snapshot()
        for fields in (dict(engine_revision="other-revision"),
                       dict(source_timestamp_ns="10000000002"),
                       dict(native_landmark_ids=(7,)), dict(engine_total_count=1),
                       dict(source_cloud_sha256="0" * 64),
                       dict(source_cloud_sha256=parse_pointcloud2(cloud([(9, 0, 2)] * 2)).source_cloud_sha256)):
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(FeatureValidationError, "EVIDENCE_MISMATCH"):
                    self.replace([(0, 0, 2)] * 2, coverage="complete", engine_total_count=2,
                        engine_revision="native-revision-1", full_snapshot_evidence=self.full_evidence(2, **fields))
                self.assertEqual(self.stream.global_snapshot(), before)

    def test_full_snapshot_proof_rejects_duplicate_invented_and_mutable_ids(self):
        for identities in ((7, 7), (True, 2), (-(2**63)-1, 2), (2**64, 2), [7, 8]):
            with self.subTest(identities=identities):
                with self.assertRaises(FeatureValidationError):
                    self.full_evidence(2, native_landmark_ids=identities)
        with self.assertRaises(FeatureValidationError):
            self.full_evidence(2, engine_total_source="")
        self.assertEqual(self.full_evidence(2, native_landmark_ids=(-1, 2)).native_landmark_ids, (-1, 2))

    def test_complete_source_remains_complete_under_display_lod_and_region_query(self):
        points = [(x, 0, 2) for x in range(100)]
        self.replace(points, coverage="complete", engine_total_count=100,
            engine_revision="native-revision-1", full_snapshot_evidence=self.full_evidence(100, points=points))
        snapshot = self.stream.global_snapshot()
        self.assertTrue(snapshot["decimation"])
        self.assertEqual(snapshot["coverage"], "complete")
        detail = self.stream.global_snapshot(region=[90, -1, 0, 99, 1, 3], limit=20)
        self.assertEqual(detail["coverage"], "complete")
        self.assertEqual(detail["displayed_count"], 10)
        self.assertEqual(detail["completeness_evidence"]["snapshot_id"], "native-snapshot-1")

    def test_static_map_age_and_session_heartbeat_are_independent(self):
        self.replace([(0, 0, 2)])
        first = self.stream.global_snapshot()
        self.stream.heartbeat(context=self.context, tracking_state="TRACKING", received_at=1000)
        frame = self.stream.frame(now_monotonic=1000.1)
        self.assertTrue(frame["stream_connected"])
        self.assertEqual(frame["global_map"]["snapshot_id"], first["snapshot_id"])
        self.assertEqual(frame["global_map"]["source_timestamp_ns"], first["source_timestamp_ns"])
        self.assertFalse(self.stream.frame(now_monotonic=1002)["stream_connected"])

    def test_deterministic_lod_retains_spatial_extents_independent_of_arrival_order(self):
        points = [(float(x), float(y), float(z)) for x in range(-10, 11)
                  for y in range(-2, 3) for z in range(4)]
        sampled = spatial_lod(points, 20)
        random.Random(42).shuffle(points)
        self.assertEqual(sampled, spatial_lod(points, 20))
        for axis in range(3):
            self.assertEqual(min(p[axis] for p in sampled), min(p[axis] for p in points))
            self.assertEqual(max(p[axis] for p in sampled), max(p[axis] for p in points))
        self.replace(points)
        self.assertEqual(self.stream.global_snapshot()["displayed_count"], 20)
        self.assertTrue(self.stream.global_snapshot()["decimation"])

    def test_region_detail_queries_do_not_claim_missing_engine_points(self):
        self.replace([(x, 0, 2) for x in range(100)], coverage="subset", backend_limit=100)
        snapshot = self.stream.global_snapshot(region=[90, -1, 0, 99, 1, 3], limit=20)
        self.assertEqual(snapshot["region_exported_count"], 10)
        self.assertEqual(snapshot["displayed_count"], 10)
        self.assertEqual(snapshot["coverage"], "subset")
        self.assertIsNone(snapshot["engine_total_count"])

    def test_old_snapshot_and_epoch_cannot_replace_current_map(self):
        self.replace([(1, 0, 2)])
        self.assertFalse(self.stream.replace_global(cloud([(9, 0, 2)], stamp=1),
            context=self.context, source_id="map", provenance="engine"))
        self.assertFalse(self.replace([(2, 0, 2)], context=StreamContext("session", 3, "previous")))
        self.assertEqual(self.stream.global_snapshot()["points"], [[1, 0, 2]])
        self.stream.reset(StreamContext("session", 3, "next"))
        self.assertIsNone(self.stream.global_snapshot())

    def test_failed_replacement_does_not_partially_publish_points(self):
        self.replace([(1, 0, 2)])
        before = self.stream.global_snapshot()
        with self.assertRaises(FeatureValidationError):
            self.replace([(9, 0, 2)], source_id="")
        self.assertEqual(self.stream.global_snapshot(), before)
        with self.assertRaisesRegex(FeatureValidationError, "BACKEND_LIMIT"):
            self.replace([(9, 0, 2)], backend_limit=0)
        self.assertEqual(self.stream.global_snapshot(), before)

    def test_trajectory_is_replaced_in_source_order_and_identifies_slam(self):
        points = [(i, i % 3, 0) for i in range(25000)]
        self.stream.replace_trajectory(points, context=self.context, stamp_ns=100,
            source_id="/engine/slam_path", provenance="engine_slam_path")
        trajectory = self.stream.frame(now_monotonic=100)["trajectory"]
        self.assertLessEqual(len(trajectory["points"]), 10_001)
        self.assertEqual(trajectory["points"][0], list(points[0]))
        self.assertEqual(trajectory["points"][-1], list(points[-1]))
        self.assertEqual(trajectory["trajectory_kind"], "slam")
        self.stream.replace_trajectory([(9, 9, 9)], context=self.context, stamp_ns=101,
            source_id="/engine/slam_path", provenance="engine_slam_path")
        self.assertEqual(self.stream.frame(now_monotonic=100)["trajectory"]["points"], [[9, 9, 9]])

    def test_bounded_wire_frames_are_detached_for_multiple_slow_consumers(self):
        stream = FeatureStream(self.context, max_wire_bytes=4096, max_global_points=500)
        stream.replace_global(cloud([(i/7, i/13, i/17) for i in range(1000)]),
            context=self.context, source_id="map", provenance="engine")
        first = stream.frame(now_monotonic=100)
        second = stream.frame(now_monotonic=101)
        self.assertLessEqual(len(json.dumps(first, separators=(",", ":")).encode()), 4096)
        self.assertTrue(first["global_map"]["wire_decimated"])
        self.assertEqual(first["global_map"]["exported_count"], 1000)
        first["global_map"]["points"].clear()
        self.assertTrue(second["global_map"]["points"])
        self.assertTrue(stream.global_snapshot()["points"])
        direct = stream.global_snapshot()
        direct["points"].clear()
        self.assertTrue(stream.global_snapshot()["points"])
        self.assertGreater(second["sequence"], first["sequence"])


if __name__ == "__main__":
    unittest.main()
