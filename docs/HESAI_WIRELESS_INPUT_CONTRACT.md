# Hesai wireless XT16 input and PTC decision

## Decision

Gate 3 uses the pinned Hesai driver directly with an exact private UDP tuple
and sensor-associated offline calibration. It does not add a receiver adapter,
PTC proxy, route, NAT, Linux bridge, multicast forwarder or generic network
configuration.

The fixed accepted path is:

```text
robot relay 192.168.50.30:46236
  -> external Orin 192.168.50.10:2368
  -> Hesai /lidar_points, frame hesai_lidar
```

The repository-owned profile is `config/hesai_xt16_wireless.yaml`. The legacy
`config/hesai_xt16.yaml` remains the wired profile and is not modified or
generalized.

## Pinned-source findings

This decision was checked against these exact revisions:

| Component | Revision |
| --- | --- |
| `HesaiTechnology/HesaiLidar_ROS_2.0` | `e7e112f0809f0eed5e3c81c55a1a0376474db234` |
| `HesaiTechnology/HesaiLidar_SDK_2.0` | `9d5dc4fc4ade5be5f6a6ca00e71dd4050b054168` |

The ROS wrapper's `source_drive_common.hpp` passes
`device_ip_address`, `device_udp_src_port`, `host_ip_address`, `udp_port`,
`use_ptc_connected`, `correction_file_path` and `firetimes_path` into the SDK.
The SDK's `SocketSource` binds `host_ip_address:udp_port` and records each UDP
peer IP and port. `hesai_lidar_sdk.hpp` enables point-packet filtering only
when `device_udp_src_port` is in `1024..65535` and `device_ip_address` is a
valid IPv4 address, then requires both values to match before parsing.

Consequently the wireless profile fixes all four endpoint values and does not
use `0.0.0.0`, a hostname, multicast, a CIDR allowlist, an arbitrary source or
a runtime network override. The upstream filter is parser-side rather than an
attached kernel BPF filter. Deployment should therefore add only an exact
host firewall allow rule for the same four-tuple and reject other traffic to
UDP 2368; the proposed rule belongs in the later deployment plan and is not
applied by Gate 3.

## PTC and calibration decision

The pinned SDK's `Lidar::Init` has an explicit offline path: with
`use_ptc_connected: false`, it calls the selected parser's local loaders
instead of opening the PTC client. The measured packet header `EE FF 06 01`
selects the SDK's `PandarXT`/UDP 6.1 (`XTM1`) parser for this marketed XT16.
That parser consumes the sensor-specific generic CSV correction. A historic
live wired log for this unit shows the same parser loading that correction and
publishing at 10 Hz while its optional firetime file was absent. Firetime is
therefore intentionally omitted from this proven baseline.

The fixed private paths are:

```text
/etc/robot-scope/hesai/xt16-correction.csv
/etc/robot-scope/hesai/xt16-calibration.manifest
```

Actual correction contents, serial numbers and hashes are not repository
data. After deployment approval, the procedure in
`docs/HESAI_XT16_CALIBRATION_RUNBOOK.md` obtains the correction for the exact
installed XT16 using only the pinned SDK's generic read-only
`GetCorrectionInfo`. It creates a private manifest containing:

```text
sensor model and serial association
driver and SDK revisions
absolute correction path, bounded measured byte length and SHA-256
acquisition time and approved acquisition method
```

The physical label supplies the private serial association because this pinned
SDK does not expose a documented generic PTC serial decoder for this contract.
A second operator must cross-check it against the mounted unit. The runtime validator rejects a
missing, symlinked, non-regular, wrong-owner/group, broadly accessible,
wrong-revision, wrong-model/path/length or hash-mismatched bundle before ROS is
sourced or the driver starts. Gate 3 did not create those files, read the
sensor serial, connect to PTC, install a profile or start the driver.

## PTC proxy verdict

A PTC proxy is not required by the selected source path and is not implemented.
It remains `BLOCKED` as a fallback unless a later, separately approved hardware
test proves that the exact offline artifacts cannot initialize this pinned
driver. Such evidence would trigger a new design review for one exact client,
one exact destination, bounded buffers, connect/idle timeouts and bounded byte
counters. It would not authorize a general TCP proxy.

## Fail-closed hardware acceptance

The profile alone is hardware-free evidence. It does not prove calibration
identity, UDP receipt, `/lidar_points` publication, point count, rate, age,
jitter, packet loss or socket drops. HW-2 remains `NOT_RUN` until HW-1 has
passed and deployment has been separately approved.

At hardware start, any missing or mismatched correction manifest, unexpected
UDP peer, PTC attempt, multiple `/lidar_points` publishers, stale cloud or
driver residue is a stop condition. Recovery never starts Mapping, FAST-LIO,
Nav2, Mission, Dataset Capture, a control lease or robot motion.
