# XT16 header-only diagnostic

## Decision

When `tcpdump`, `tshark` and `dumpcap` are absent, use the repository's fixed
`scripts/inspect_xt16_udp_headers.py` diagnostic. Python exposes Linux
`AF_PACKET`, while Linux requires `CAP_NET_RAW` for packet sockets. The tool is
therefore invoked with `sudo`, but it has no operational arguments and opens
only one `AF_PACKET/SOCK_DGRAM` socket on fixed `eth0`.

The audit lasts at most eight seconds, stops after 40 relevant UDP headers and
retains at most 16 distinct tuples. It reports only source/destination IP and
port, UDP payload length, packet type and count. It does not enable
promiscuous mode, store or print payload bytes, write a capture file, transmit
packets, or change an interface, route, firewall, service or LiDAR setting.

Primary references:

- Linux `packet(7)`: <https://man7.org/linux/man-pages/man7/packet.7.html>
- Python `socket` AF_PACKET address contract:
  <https://docs.python.org/3/library/socket.html>

## Current gate

The installed robot-side relay requires
`192.168.123.20:10000 -> 192.168.123.18:2368`. On 2026-09-07 it captured
packets but accepted and forwarded zero, with only `packet_type` and
`ip_address` rejection counters increasing. The header-only audit is used to
identify the actual tuple before proposing any configuration change. Its
result does not authorize a relay, LiDAR, Mapping, D2 provider, Nav2 or control
mutation.

The read-only XT16 Web Control audit subsequently found destination
`192.168.123.99:2368`, while the current robot-side receiver is
`192.168.123.18:2368`. Restoring only that destination produced advancing
accepted and forwarded relay counters immediately; the device's separate
Stream IP setting did not require a change. This establishes configuration
drift as the missing raw-packet cause, without weakening the relay tuple
allowlist.

The first external preview restart then failed the one-publisher gate. A
bounded DDS header audit tied the extra endpoint GUID to another team's
multi-homed wired workstation, advertised from both `192.168.50.110` and its
sensor NIC `192.168.123.99`. The other workstation was not changed. Wireless
Robot Scope processes now use `ROS_LOCALHOST_ONLY=1`: `eno1=192.168.50.10/24`
remains mandatory for the fixed authenticated/bounded transports, while DDS
discovery and the local Hesai -> cloud bridge -> FAST-LIO/Nav2 graph remain on
the external Jetson. Direct-wired profiles retain their existing DDS binding.

This matches the ROS 2 environment contract for classrooms or shared networks,
where localhost-only discovery prevents same-name topics from other computers:
<https://docs.ros.org/en/foxy/Tutorials/Beginner-CLI-Tools/Configuring-ROS2-Environment.html#the-ros-localhost-only-variable>.

Run from the exact repository release or copy only this reviewed script to a
private temporary path, then execute:

```bash
sudo /usr/bin/python3 scripts/inspect_xt16_udp_headers.py
```

After recording the bounded text output, remove any temporary copy. Do not
install a packet-capture package solely for this check.
