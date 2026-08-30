# Robot Scope competition system architecture

## Purpose and authority

This document freezes the competition deployment baseline for the dual-Jetson
system. It complements the current software ownership authority in
[ARCHITECTURE.md](ARCHITECTURE.md) and the existing deployment variants in
[TOPOLOGY.md](TOPOLOGY.md). It does not claim that later competition work
packages are already implemented.

The baseline was reconciled with repository HEAD `79f41b6` and the deployed
hardware observations recorded in
[HARDWARE_VALIDATION_2026-08-30.md](HARDWARE_VALIDATION_2026-08-30.md).

## Fixed physical roles

```text
RealSense D435i
  └─ USB → robot-side Jetson, Ubuntu 20.04
              ├─ camera capture and bounded relay
              ├─ Go2-local DDS/control bridge
              └─ future sensor-local shadow inference
                    │
                    │ trusted competition Wi-Fi
                    ▼
               ipTIME BE5100M
                    │ Ethernet
                    ▼
external Jetson Orin Nano, Ubuntu 22.04 / ROS 2 Humble
  ├─ Robot Scope web/API
  ├─ result validation, Mission and Safety coordination
  ├─ Dataset, model registry, diagnostics and logs
  └─ mapping/navigation only after their sensor-data gate passes
                    │ trusted management LAN
                    ▼
operator laptop
  ├─ browser and maintenance
  └─ dataset export, labeling, training and deployment preparation
```

The laptop and Internet are not required for the competition runtime to keep
running. Losing either must never cause automatic motion continuation or
automatic re-arming.

## Address vocabulary

New competition code and documentation use role names unless describing a
verified deployment record:

| Placeholder | Role |
| --- | --- |
| `<ROBOT_SIDE_IP>` | robot-side Jetson management Wi-Fi address |
| `<DASHBOARD_HOST_IP>` | external Orin management Ethernet address |
| `<ROUTER_IP>` | trusted BE5100M management address |
| `<ROBOT_SCOPE_PORT>` | Robot Scope HTTP port, normally 8088 |
| `<ROBOT_WIFI_IFACE>` | robot-side management Wi-Fi interface |
| `<DASHBOARD_IFACE>` | external Orin management Ethernet interface |

The 2026-08-30 hardware record observed `<ROBOT_SIDE_IP>=192.168.50.30` and
`<DASHBOARD_HOST_IP>=192.168.50.10`. Those are deployment evidence, not new
portable defaults. The Go2/sensor LAN remains a separate device contract and
must not be silently merged into the management LAN.

## Responsibility boundary

| Capability | Robot-side Jetson | External Orin | Laptop |
| --- | --- | --- | --- |
| D435i device and capture timestamp | owner | receiver only | none |
| Camera preview production | owner | bounded receiver and browser fan-out | viewer |
| Go2 camera RTP access | fixed camera-only relay | decoder and browser fan-out | viewer |
| Go2 DDS participant | owner in the accepted wireless topology | no generic DDS route | none |
| Signed control bridge | robot-side owner | lease, intent and lifecycle coordinator | input client |
| Lane/YOLO/depth inference | future shadow candidate | validator/comparison candidate | training only |
| Mission/Safety coordination | never | final software owner | operator UI only |
| Dataset sessions | no long-term duplicate by default | authoritative writer | export/label/train |
| Model registry/activation | verified local runtime package | authoritative registry | build candidate |
| FAST-LIO/Nav2 | not moved implicitly | current product owner, but wireless input is blocked | none |

The control split is intentional: the external Orin owns browser intent,
manual/autonomous exclusion and Mission coordination, while the robot-side
bridge owns the Go2-local DDS publisher and watchdog. The authenticated fixed
UDP envelope described by
[ADR_WIRELESS_CONTROL_TRANSPORT.md](ADR_WIRELESS_CONTROL_TRANSPORT.md) connects
only those existing control messages; it is not a ROS or DDS router.

## Data flows

### Implemented competition baseline

```text
D435i RGB
  → robot-side on-demand MJPEG relay
  → external Orin fixed receiver
  → same-origin camera WebSocket
  → browser

Go2 H.264 multicast
  → robot-side fixed RTP validator/copy
  → external Orin decoder
  → same-origin camera WebSocket
  → browser

browser/Mission intent
  → external ControlManager
  → signed fixed UDP envelope
  → robot-side watchdog bridge
  → fixed Go2 sport request path
```

Camera and control paths remain independent. A camera failure cannot relax a
control freshness or watchdog rule.

### Planned perception result flow

```text
D435i latest frame
  → sensor-local SHADOW inference
  → typed bounded result + health + model identity
  → external validation and stale gate
  → Cockpit and optional dataset metadata
```

No perception result may publish a motor command or acquire a control lease.

### Point-cloud modes

| Mode | Purpose | Default |
| --- | --- | --- |
| `OFF` | no management-Wi-Fi cloud traffic | yes |
| `SUMMARY` | bounded distance, obstacle or free-space result | preferred |
| `DECIMATED_DIAGNOSTIC` | supervised bounded points/rate/fields | approval required |
| `RAW_DIAGNOSTIC` | temporary near-raw investigation | separate load approval required |

The current external dashboard has zero `/velodyne_points` publishers in the
accepted wireless topology. Its existing XT16/FAST-LIO launcher correctly
fails because the external host does not own the former sensor-LAN address.
WP00 does not resolve that gap. A later design must either colocate the mapping
worker with sensor access or add a bounded, measured sensor-data contract. A
broad route, NAT, Linux bridge or generic DDS router is not an acceptable
implicit fix.

## Safety authority

The authority order remains:

1. physical remote/E-stop and supervised operating procedure;
2. robot firmware stop behavior;
3. robot-side control watchdog and exact graph cardinality;
4. external lease, deadman, freshness and Mission/Navigation coordination;
5. perception as observation only.

AI readiness, camera LIVE state, Wi-Fi association and a running systemd unit
cannot replace authenticated bridge readiness. Reconnect, browser reload,
model reload and stale-result recovery never auto-arm or auto-resume motion.

## Current assumptions versus competition target

| Repository assumption or behavior | Classification | Competition disposition |
| --- | --- | --- |
| D435i physically owned by robot-side Jetson | matches | preserve single device owner |
| RealSense bind/dashboard hosts are explicit private IPv4 settings | deployment setting | keep fail-closed allowlist; remove reference defaults only through WP01 tests |
| Go2 camera copy has fixed verified `.50.30 → .50.10` constants | code change needed | preserve packet validation while introducing a reviewed role-based contract |
| Signed control datagram peers are explicit private settings | matches | preserve port, HMAC, lease and watchdog contracts |
| Robot-side Foxy bridge owns Go2 DDS in wireless mode | matches | document as the competition control host |
| External Orin owns Dataset Capture and private session files | matches | preserve quotas, reserve and atomic finalization |
| External Orin directly owns `192.168.123.99/24` for XT16/FAST-LIO | code/architecture change needed | current wireless deployment is blocked; decide a bounded data path later |
| Raw PointCloud is a normal live-view input when directly wired | deployment-dependent | management Wi-Fi default becomes `OFF`; diagnostic modes require gates |
| Sensor-local inference runtime exists | code change needed | add shadow-only runtime in later WPs |
| Laptop/browser is needed to operate the UI | matches | it is a client, not a runtime or motion dependency |
| Router DHCP reservation is configured | hardware confirmation needed | one reboot retained the lease; router configuration and competition reboot repetition remain unverified |
| Full-course Wi-Fi capacity is sufficient | hardware confirmation needed | 60-minute soak/interference and location matrix remain pending |

## Repository evidence inventory

| Evidence | Existing assumption | Classification |
| --- | --- | --- |
| `config/go2.json`, `scripts/run_go2_humble.sh`, discovery/UI defaults | Go2 reference target is `192.168.123.161` | device/reference setting; runtime target remains explicit and pinned |
| `scripts/realsense_mjpeg_relay.py`, `remote_mjpeg_camera.py`, service env example | `.123.18` relay and `.123.99` receiver are defaults, with strict private-IP runtime overrides | deployment setting; WP01 must preserve exact allowlists |
| `scripts/go2_camera_rtp_relay.py` | capture `.123.18`, source Go2, relay `.50.30` and dashboard `.50.10` are fixed constants | code change needed for another competition address plan |
| `control_datagram.py` and the robot-side control env example | port 46010 is fixed; bind/peer are explicit private addresses | matches competition boundary |
| `setup_go2_ros2_foxy.sh` and robot-side service | Foxy DDS binds to robot-side `.123.18/24` | matches accepted wireless control topology |
| `setup_go2_ros2_humble.sh`, `run_hesai_fastlio_humble.sh`, doctor and dashboard env example | external Orin must own `.123.99/24` | incompatible with the current management-only external Orin |
| `scripts/xt16_udp_relay.py` and Hesai config | fixed XT16 `.123.20 → .123.18 → .123.99` lab packet path | code/architecture change needed for wireless competition use |
| `dataset_capture.py`, application runtime and run scripts | Dataset writer and private storage live with Robot Scope | matches external-Orin ownership |
| `mapping_jobs.py`, `navigation_jobs.py` and application coordinators | FAST-LIO/Nav2 children live with Robot Scope | product ownership matches, but live wireless inputs are blocked |
| `ADR_WIRELESS_CONTROL_TRANSPORT.md` and lifecycle deployment | external Orin coordinates a robot-side bridge through signed UDP and restricted SSH lifecycle | matches; preserve rather than reverting to same-host assumptions |

## Degraded behavior

- Wi-Fi loss: camera/perception become stale, diagnostic cloud stops first,
  control remains governed by existing fail-closed status and watchdogs.
- Robot-side inference loss: camera relay remains independent; result becomes
  offline and cannot be reused.
- External Robot Scope loss: robot-side inference does not inherit Mission or
  motion ownership; recovery requires explicit operator state review.
- Laptop loss: browser lease fails closed; server-side finalized data remains
  on the external Orin according to its existing policy.
- Model mismatch or unknown hash: shadow result is rejected, not relabeled as
  active.

## Hardware confirmations still required

- BE5100M reservation and lease retention across the competition reboot plan.
- Full-course RSSI, loss, RTT percentiles and interference behavior.
- Robot-side CPU/GPU/RAM/thermal headroom with relay plus each shadow model.
- Timestamp/sequence alignment for camera and future perception results.
- The selected XT16/FAST-LIO placement and its bounded wireless data budget.
- Supervised motion/fault rows that remain pending in
  [HARDWARE_ACCEPTANCE.md](HARDWARE_ACCEPTANCE.md).
