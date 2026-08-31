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
`use_ptc_connected: false`, it calls the selected XT16 parser's local
correction and firetime loaders instead of opening the PTC client. The generic
parser describes correction data as necessary for packet decoding. Firetime
data enables per-channel timing correction and is kept mandatory in this
product profile so that hardware acceptance does not silently use reduced
timing fidelity.

The fixed private paths are:

```text
/etc/robot-scope/hesai/xt16-correction.csv
/etc/robot-scope/hesai/xt16-firetime.csv
/etc/robot-scope/hesai/xt16-calibration.manifest
```

Actual calibration contents, serial numbers and hashes are not repository
data. Before deployment, an approved sensor-side procedure must obtain the
files for the exact installed XT16 and create a private manifest containing:

```text
sensor model and serial association
driver and SDK revisions
absolute correction and firetime paths
SHA-256 of both files
acquisition time and approved acquisition method
```

The installer must reject missing, symlinked, non-regular, writable-by-group,
writable-by-other or hash-mismatched artifacts. Gate 3 does not create those
files, read the sensor serial, connect to PTC, install a profile or start the
driver.

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

At hardware start, any missing or mismatched calibration manifest, unexpected
UDP peer, PTC attempt, multiple `/lidar_points` publishers, stale cloud or
driver residue is a stop condition. Recovery never starts Mapping, FAST-LIO,
Nav2, Mission, Dataset Capture, a control lease or robot motion.
