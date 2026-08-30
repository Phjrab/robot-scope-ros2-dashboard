# Competition network and data-flow budget

## Scope

This document defines the planning budget and measurement contract for the
robot-side Wi-Fi bottleneck. It does not declare an unmeasured link to be
accepted. Existing network roles and current verified examples are documented
in [TOPOLOGY.md](TOPOLOGY.md); the competition role vocabulary is defined in
[COMPETITION_SYSTEM_ARCHITECTURE.md](COMPETITION_SYSTEM_ARCHITECTURE.md).

## Network zones

```text
robot-side Jetson <ROBOT_WIFI_IFACE>/<ROBOT_SIDE_IP>
        │ camera + signed control + future typed results
        │ trusted competition Wi-Fi
        ▼
BE5100M <ROUTER_IP>
        │ Ethernet
        ▼
external Orin <DASHBOARD_IFACE>/<DASHBOARD_HOST_IP>:<ROBOT_SCOPE_PORT>
        │ trusted management LAN
        ▼
operator laptop
```

The robot/sensor Ethernet remains a separate non-default-route device network.
Management Wi-Fi must not gain a broad route, NAT, bridge, multicast forwarder
or generic DDS router merely to make a sensor appear on the dashboard.

## Traffic classes and priority

| Priority | Traffic | Competition policy |
| ---: | --- | --- |
| 1 | signed control/status and stop-related freshness | fixed small messages; never relaxed |
| 2 | typed perception result and health | bounded schema/rate/age |
| 3 | camera preview | bounded resolution/FPS/quality, demand scoped |
| 4 | Dataset export/model transfer | pause during active competition work |
| 5 | decimated cloud | supervised diagnostic session only |
| 6 | raw cloud | separate overload approval only |

The control bridge still relies on its existing HMAC, lease, graph,
LowState-age and watchdog contracts. Network optimization cannot enlarge those
timeouts or bypass readiness.

## Baseline calculations

The RealSense relay is currently bounded to 640×480, 15 FPS and JPEG quality
72. Its approximate payload rate is:

```text
MJPEG bits/s = average JPEG bytes × frames/s × 8
```

| Average JPEG | 15 FPS payload only |
| ---: | ---: |
| 40 KiB | about 4.9 Mbps |
| 100 KiB | about 12.3 Mbps |
| 200 KiB | about 24.6 Mbps |

TCP, HTTP and Wi-Fi overhead and retransmission are additional. A LIVE label
and average throughput are insufficient; source/receive age and reconnect
behavior are required.

For raw YUY2 or Z16:

```text
bits/s = width × height × bytes/pixel × FPS × 8
640 × 480 × 2 × 15 × 8 = 73.728 Mbps
```

Raw color plus depth at that geometry is about 147.456 Mbps before overhead.

For PointCloud2:

```text
bits/s = point count × point_step × FPS × 8
```

| Points | Bytes/point | FPS | Payload only |
| ---: | ---: | ---: | ---: |
| 100,000 | 16 | 10 | 128 Mbps |
| 100,000 | 32 | 10 | 256 Mbps |
| 50,000 | 16 | 5 | 32 Mbps |

The real `point_step`, fields, framing and loss behavior must be measured from
the chosen source. Router branding or PHY link rate is not acceptance evidence.

## Point-cloud modes and guards

| Mode | Required bounds | Automatic failure action |
| --- | --- | --- |
| `OFF` | no cloud packets on management Wi-Fi | none; default |
| `SUMMARY` | typed result, fixed size/rate/age | mark stale and discard |
| `DECIMATED_DIAGNOSTIC` | point/rate/field/queue/TTL caps | stop diagnostic stream first |
| `RAW_DIAGNOSTIC` | fixed source, explicit duration and link headroom | abort on any priority-1/2/3 degradation |

No mode may reuse a stale cloud, accumulate an unbounded queue or auto-enable
after reconnect.

## Initial measurement targets

These are planning targets pending a competition-course report, not runtime
timeout changes:

- RSSI target: at least -65 dBm throughout the measured course;
- packet-loss target: at most 0.5%;
- RTT target: p95 at most 30 ms and p99 at most 80 ms;
- sustained application payload target: at most 30–40% of the minimum observed
  stable throughput, retaining headroom for contention and retransmission.

No single target produces PASS. Camera age, result age, LowState/control
freshness and service stability must pass in the same test interval.

## Test matrix

| ID | Camera | AI | PointCloud | Control/status | Purpose |
| --- | --- | --- | --- | --- | --- |
| A | off | off | off | off | Wi-Fi baseline |
| B | MJPEG | off | off | off | camera load |
| C | MJPEG | off | off | telemetry | coexistence |
| D | MJPEG | shadow | off | telemetry | sensor-local inference |
| E | low preview | shadow | summary | telemetry | preferred competition mode |
| F | low preview | shadow | decimated | telemetry | supervised diagnostic |
| G | preview | shadow | raw | telemetry | separately approved overload test |

Repeat each approved row at the start, furthest point, shielded/interference
point and representative robot orientation. The deferred 60-minute wireless
soak remains a separate requirement.

Record at least:

```text
timestamp and location
RSSI and negotiated link rate
RTT p50/p95/p99 and loss
application tx/rx bitrate and retransmission evidence
camera source/receiver FPS and age
perception input/result age and inference p50/p95
LowState and signed bridge age
CPU/GPU/RAM, temperature and throttling
diagnostic-cloud points/rate/drop, when enabled
```

## Existing configuration contract inventory

| Area | Current contract | WP00 classification |
| --- | --- | --- |
| RealSense relay | explicit private/link-local bind and one dashboard host | deployment-configurable and fail closed |
| signed control UDP | explicit private bind/peer on fixed port 46010 | deployment-configurable and fail closed |
| Go2 camera RTP copy | fixed verified interfaces/addresses/ports in code | needs reviewed WP01 portability without arbitrary forwarding |
| XT16 UDP copy | fixed `.123.18 → .123.99` lab contract | incompatible with current management-only external Orin |
| Dashboard Go2 interface | defaults to `eno1` and `.123.99/24` | direct-wired reference, not current wireless fact |
| Dataset path | external-Orin private absolute/root-derived path | local filesystem, not continuous Wi-Fi traffic |

WP01 may replace reference address defaults only where it can preserve strict
private-address validation, exact peers and bounded transport. It must not turn
any relay into an arbitrary destination or public listener.

## Degradation order

When the link budget is exceeded:

1. stop raw diagnostic cloud;
2. reduce or stop decimated diagnostic cloud;
3. pause Dataset/model transfer;
4. reduce preview FPS, then resolution/quality under an explicit profile;
5. reduce shadow inference rate or disable the model;
6. preserve control/LowState safety rules unchanged.

## Hardware confirmation still required

- BE5100M channel width, client isolation, reservation and offline behavior;
- full-course RSSI/RTT/loss and 60-minute soak;
- camera bitrate and retransmission under representative scenes;
- priority-traffic behavior during diagnostic-cloud overload;
- reconnect behavior with no auto-arm or stale-result reuse.
