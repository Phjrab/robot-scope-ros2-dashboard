# Passive LiDAR, XYZ, IMU and odometry samples

Real sensor messages retained during an approximately 10-second passive capture
on 2026-10-22 at 15:39 UTC (2026-10-23 at 00:39 KST). Public upload of these
collected sensor data was explicitly authorized by the data owner.

This is a sparse sample package: only message sequence **1, 30 and 70 within each
topic** was retained. It is not a continuous bag or a synchronized multi-sensor
sequence. Equal sequence numbers across different topics do not establish
simultaneity. The operator confirmed stationarity; it was not independently
measured. This package provides no absolute pose or accuracy ground truth.

| Topic | Message type | Retained | Received during capture |
|---|---|---:|---:|
| `/lidar_points` | `sensor_msgs/msg/PointCloud2` | 3 | 100 |
| `/velodyne_points` | `sensor_msgs/msg/PointCloud2` | 3 | 100 |
| `/imu/body` | `sensor_msgs/msg/Imu` | 3 | 4,536 |
| `/utlidar/robot_odom` | `nav_msgs/msg/Odometry` | 3 | 1,499 |

The received totals describe the original collector window, not the number of
messages downloadable here. No new collection or sensor operation occurred for
this publication.

## Files and coordinates

All 42 sample files are copied byte-for-byte from the frozen capture. The added
`MANIFEST.json` supplies file sizes and SHA256 hashes; original per-message JSON
also records source and receipt timestamps, frames and payload hashes.

- `.cdr`: original serialized ROS 2 subscription bytes, not reserialized messages.
  Deserialize using the message type recorded in the matching `.json`.
- `.json`: original per-message metadata and bounded decoded IMU/odom diagnostics.
- `.pointcloud2-data.bin`: original PointCloud2 data field, including point
  attributes and source order. Use the field offsets and layout in the JSON.
- `.xyz-f64le.bin`: headerless little-endian float64 XYZ triples in original row
  order, all rows retained. No transform, filtering or selection is applied.
- `.npz`: saved float32 XYZ and metadata. Load with `numpy.load(...,
  allow_pickle=False)`; `points` is an N-by-3 XYZ array. It does not contain
  intensity, ring or per-point time; use `.pointcloud2-data.bin` and its JSON
  layout for those attributes. This is a convenience export of the same cloud.

The raw `/lidar_points` clouds each have 64,000 points with 26-byte records:
float32 x/y/z/intensity at offsets 0/4/8/12, uint16 ring at 16, float64 timestamp
at 18. The converted `/velodyne_points` clouds each have 16,000 points with
22-byte records: x/y/z/intensity at 0/4/8/12, float32 relative time at 16,
uint16 ring at 20. Both are little-endian and use `hesai_lidar` frames.

Raw here means received PointCloud2 messages; no LiDAR UDP packet archive is
included. IMU is the received `/imu/body` stream, not a separate device-native
packet recording. Odom uses `odom` with child `base_link`; the presence of these
frame names does not independently validate body pose or extrinsics.

Zero XYZ rows are retained. Units follow ROS conventions; physical scale,
calibration and the relationship between source clocks remain unverified.
Receipt wall/monotonic timestamps are local callback times, not synchronization
proof. Preserve nanosecond integer values with an integer-safe parser; ordinary
JavaScript numbers cannot represent all these values exactly. Publisher graph
observations in metadata are separate from unavailable per-message DDS identity.

For XYZ, for example:

```python
import numpy as np
xyz = np.fromfile('lidar_points__000001.xyz-f64le.bin', dtype='<f8').reshape(-1, 3)
```

No saved reference map, registration candidates, process dumps, credentials,
private machine configuration, or ring-selection prototype is included. No
product behavior or robot deployment is changed by this data-only publication.
