"""Synthetic offline evidence tests; these do not exercise ROS or a GPU."""
import json
from contextlib import closing
import importlib.util
from pathlib import Path
import runpy
import sqlite3
import struct
import tempfile
import unittest

API = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                       'experiments/isaac_vslam/inspect_bag.py'))


def header_cdr(sec, nano, frame, endian='<'):
    encoded = frame.encode() + b'\0'
    return (b'\x00\x01\x00\x00' if endian == '<' else b'\x00\x00\x00\x00') + \
        struct.pack(endian + 'iII', sec, nano, len(encoded)) + encoded


class CdrHeaderTests(unittest.TestCase):
    def test_both_endian_encodings_and_negative_seconds(self):
        for endian in ('<', '>'):
            self.assertEqual(API['cdr_header'](header_cdr(-2, 5, 'left_optical', endian)),
                             (-1999999995, 'left_optical'))

    def test_malformed_headers_fail_closed(self):
        for data in (b'', b'\x00\x03' + b'\0' * 30,
                     header_cdr(1, 1000000000, 'f'), header_cdr(1, 0, 'frame')[:-1]):
            with self.assertRaises(ValueError):
                API['cdr_header'](data)


class BagInspectionTests(unittest.TestCase):
    def test_static_tf_all_messages_and_segment_counts_are_preserved(self):
        def tf(parent, child, x):
            return {'transforms': [{'header': {'frame_id': parent}, 'child_frame_id': child,
                                    'transform': {'translation': {'x': x, 'y': 0.0, 'z': 0.0},
                                                  'rotation': {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0}}}]}
        def decode(data, typ):
            if typ == 'tf2_msgs/msg/TFMessage':
                return json.loads(data)
            stamp, frame = API['cdr_header'](data)
            return {'header': {'frame_id': frame}, 'encoding': 'mono8', 'height': 2, 'width': 2, 'step': 2}
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for index in range(2):
                with closing(sqlite3.connect(directory / f'bag_{index}.db3')) as con:
                    con.execute('create table topics (id integer,name text,type text)')
                    con.execute('create table messages (topic_id integer,timestamp integer,data blob)')
                    con.executemany('insert into topics values (?,?,?)',
                                    [(1, '/left/image', 'sensor_msgs/msg/Image'),
                                     (2, '/tf_static', 'tf2_msgs/msg/TFMessage')])
                    for tick in range(2):
                        stamp = 1000000000 + (2*index + tick)*33333333
                        con.execute('insert into messages values (?,?,?)',
                                    (1, stamp+1000000, header_cdr(stamp//1000000000, stamp%1000000000, 'left')))
                    con.execute('insert into messages values (?,?,?)',
                                (2, 1000000000+index, json.dumps(tf('camera', 'left' if index == 0 else 'right', .05*index)).encode()))
                    con.commit()
            result = API['inspect'](directory, decode, {'backend': 'synthetic'})
            row = result['topics']['/left/image']
            self.assertEqual(row['count'], 4)
            self.assertEqual(row['header_statistics']['sample_count'], 4)
            self.assertAlmostEqual(row['header_statistics']['mean_stamp_fps'], 30.0, places=5)
            self.assertEqual(row['header_statistics']['recorder_minus_header_ms_NOT_LATENCY']['p95'], 1.0)
            self.assertEqual({entry['child'] for entry in result['static_transform_inventory']}, {'left', 'right'})
            self.assertEqual(len(result['files']), 2)

    def test_camera_info_issues_are_reported_without_claiming_calibration(self):
        issues = API['camera_info_issues']({'width': 640, 'height': 480,
                                          'k': [0.0]*9, 'r': [float('nan')]*9, 'p': [0.0]*12})
        self.assertEqual(len(issues), 2)


@unittest.skipUnless(importlib.util.find_spec('rosbags'), 'optional rosbags backend not installed')
class RosbagsBackendTests(unittest.TestCase):
    def test_real_humble_cdr_serialization_is_decoded_offline(self):
        import numpy as np
        from rosbags.typesys import Stores, get_typestore
        store = get_typestore(Stores.ROS2_HUMBLE)
        types = store.types
        header = types['std_msgs/msg/Header'](types['builtin_interfaces/msg/Time'](10, 500), 'fixture_left')
        image = types['sensor_msgs/msg/Image'](header, 2, 2, 'mono8', 0, 2, np.zeros(4, dtype=np.uint8))
        roi = types['sensor_msgs/msg/RegionOfInterest'](0, 0, 0, 0, False)
        info = types['sensor_msgs/msg/CameraInfo'](
            header, 2, 2, 'plumb_bob', np.zeros(5),
            np.array([2., 0, 1, 0, 2, 1, 0, 0, 1]), np.eye(3).flatten(),
            np.array([2., 0, 1, 0, 0, 2, 1, 0, 0, 0, 1, 0]), 0, 0, roi)
        transform = types['geometry_msgs/msg/TransformStamped'](
            types['std_msgs/msg/Header'](types['builtin_interfaces/msg/Time'](0, 0), 'fixture_left'),
            'fixture_right', types['geometry_msgs/msg/Transform'](
                types['geometry_msgs/msg/Vector3'](.05, 0., 0.),
                types['geometry_msgs/msg/Quaternion'](0., 0., 0., 1.)))
        tf = types['tf2_msgs/msg/TFMessage']([transform])
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with closing(sqlite3.connect(directory / 'synthetic.db3')) as con:
                con.execute('create table topics (id integer,name text,type text)')
                con.execute('create table messages (topic_id integer,timestamp integer,data blob)')
                for tid, topic, typ, msg in (
                    (1, '/left/image', 'sensor_msgs/msg/Image', image),
                    (2, '/left/info', 'sensor_msgs/msg/CameraInfo', info),
                    (3, '/tf_static', 'tf2_msgs/msg/TFMessage', tf),
                ):
                    con.execute('insert into topics values (?,?,?)', (tid, topic, typ))
                    con.execute('insert into messages values (?,?,?)',
                                (tid, 10000000500, bytes(store.serialize_cdr(msg, typ))))
                con.commit()
            decode, metadata = API['decoder']('rosbags')
            result = API['inspect'](directory, decode, metadata)
            self.assertEqual(result['decoder']['backend'], 'rosbags')
            self.assertEqual(result['topics']['/left/image']['first']['header']['frame_id'], 'fixture_left')
            variants = list(result['topics']['/left/info']['calibration_variants'].values())
            self.assertEqual(variants[0]['issues'], [])
            self.assertEqual(result['static_transform_inventory'][0]['variants'][0]['translation']['x'], .05)
            json.dumps(result, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
