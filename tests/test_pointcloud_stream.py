import struct
import unittest

from robot_dashboard.pointcloud_stream import (
    MAX_POINT_BYTES,
    PointCloudFrameError,
    decode_pointcloud_frame,
    encode_pointcloud_frame,
)


class PointCloudStreamCodecTests(unittest.TestCase):
    def test_round_trip_keeps_metadata_and_packed_xyz(self):
        points = struct.pack("<6f", 1.0, -2.0, 3.5, 4.25, 5.0, -6.0)
        frame = encode_pointcloud_frame(
            {
                "seq": 17,
                "stream_id": "test-stream",
                "topic": "/Laser_map",
                "bounds": {"min": [1.0, -2.0, -6.0], "max": [4.25, 5.0, 3.5]},
                "points": [999],
                "points_bytes": b"not-public",
            },
            points,
        )

        metadata, decoded = decode_pointcloud_frame(frame)
        self.assertEqual(decoded, points)
        self.assertEqual(metadata["seq"], 17)
        self.assertEqual(metadata["stream_id"], "test-stream")
        self.assertEqual(metadata["point_count"], 2)
        self.assertEqual(metadata["encoding"], "float32le")
        self.assertTrue(metadata["prevalidated"])
        self.assertNotIn("points", metadata)
        self.assertNotIn("points_bytes", metadata)

    def test_rejects_truncated_or_tampered_frames(self):
        frame = encode_pointcloud_frame({"seq": 1}, struct.pack("<3f", 1, 2, 3))
        for invalid in (
            frame[:10],
            b"NOPE" + frame[4:],
            frame[:-1],
        ):
            with self.subTest(length=len(invalid)):
                with self.assertRaises(PointCloudFrameError):
                    decode_pointcloud_frame(invalid)

        tampered = bytearray(frame)
        tampered[12:16] = (24).to_bytes(4, "little")
        with self.assertRaises(PointCloudFrameError):
            decode_pointcloud_frame(bytes(tampered))

    def test_encoder_enforces_immutable_bounded_xyz_and_finite_json(self):
        with self.assertRaisesRegex(PointCloudFrameError, "immutable"):
            encode_pointcloud_frame({"seq": 1}, bytearray(12))  # type: ignore[arg-type]
        with self.assertRaisesRegex(PointCloudFrameError, "triples"):
            encode_pointcloud_frame({"seq": 1}, b"bad")
        with self.assertRaisesRegex(PointCloudFrameError, "one-million"):
            encode_pointcloud_frame({"seq": 1}, b"\0" * (MAX_POINT_BYTES + 12))
        with self.assertRaisesRegex(PointCloudFrameError, "valid JSON"):
            encode_pointcloud_frame({"seq": 1, "bad": float("nan")}, b"")
        with self.assertRaisesRegex(PointCloudFrameError, "metadata"):
            encode_pointcloud_frame({"seq": 1, "large": "x" * 20_000}, b"")


if __name__ == "__main__":
    unittest.main()
