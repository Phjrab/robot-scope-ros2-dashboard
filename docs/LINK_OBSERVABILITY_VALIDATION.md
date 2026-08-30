# Competition link observability validation

## Scope and safety boundary

This worksheet validates the WP02 camera/link observability contract. It does
not authorize robot motion, navigation, mapping, network reconfiguration,
service restart, cable removal or an `iperf` server/client. Every hardware row
must be started and stopped by the operator under the approval that applies to
that row. Existing control, LowState, lease, deadman and timeout contracts are
not changed by a bandwidth result.

## Bounded metric contract

| Layer | Metrics | Bound and clock domain |
|---|---|---|
| robot relay | source state, FPS, payload Mbps, frames, invalid frames, profile, viewer/process state | 5-second window, at most 120 samples, `relay_monotonic` |
| robot Wi-Fi | RSSI, negotiated TX link rate, interface state | optional cached fixed-argv probe, 1-second timeout, 4096-byte stdout cap |
| dashboard receiver | network bytes/Mbps, complete-JPEG FPS/age, reconnects, accept failures | 5-second window, at most 120 samples, `dashboard_monotonic` |
| browser decoder | successes, failures, superseded latest-only frames, queue depth | one active plus one pending frame maximum |

Relay and dashboard monotonic clocks are different domains. The dashboard must
show `UNVERIFIED_CLOCK_DOMAIN` for cross-host end-to-end latency until a
separate clock-synchronization procedure is approved and verified. Source age
and receiver age remain valid within their own hosts; they must not be
subtracted from each other.

The status vocabulary is `LIVE`, `DEGRADED`, `STALE`, `OFFLINE`, and
`UNVERIFIED`. Missing executables, malformed health JSON, non-finite values and
probe timeouts fail to `UNVERIFIED`; they do not widen a timeout or retry queue.

## Dashboard check

Open **Sensors → Camera stream** and select the source under test. Record the
four cards together:

1. `ROBOT WI-FI`: RSSI, negotiated link rate and probe state.
2. `REALSENSE SOURCE`: robot-side source FPS, source age and configured profile.
3. `TRANSPORT`: dashboard receive Mbps/FPS and reconnect counter.
4. `DECODE`: browser decode success/failure, superseded frames and queue depth.

The camera being visually LIVE is not sufficient. A stale source age,
increasing reconnect/failure counter, persistent queue depth of two, or a
missing required metric is recorded separately. Do not claim end-to-end
latency while the clock-domain strip remains unverified.

## Manual matrix A–G

| ID | Camera | AI | Point cloud | Control/status | Operator action required | Expected observation |
|---|---|---|---|---|---|---|
| A | off | off | off | off | observe idle link only | Wi-Fi baseline; source/transport offline or idle |
| B | MJPEG | off | off | off | open one RealSense viewer | one producer/viewer, bounded camera bitrate |
| C | MJPEG | off | off | telemetry | enable approved read-only telemetry | no camera age/reconnect regression |
| D | MJPEG | shadow | off | telemetry | start approved shadow inference | source and result ages remain bounded |
| E | low preview | shadow | summary | telemetry | use approved competition profile | preferred coexistence candidate |
| F | low preview | shadow | decimated | telemetry | separately approve diagnostic cloud | stop cloud first on degradation |
| G | preview | shadow | raw | telemetry | separate overload approval required | diagnostic only; never acceptance default |

Run each approved row at the start point, furthest point, interference/shielded
point and representative robot orientation. The deferred 60-minute wireless
soak is a separate task and is not satisfied by this worksheet.

## Record for every approved run

```text
date/time:
operator and approval:
matrix row / location / orientation:
robot and dashboard addresses/interfaces (no credentials):
camera profile:
ROBOT WI-FI state / RSSI / link Mbps:
SOURCE state / FPS / age / payload Mbps / invalid frames:
TRANSPORT state / receive FPS / receive Mbps / reconnects:
DECODE state / success / failure / superseded / queue depth:
clock-domain label:
RTT/loss measurement method and p50/p95/p99 (if separately approved):
control/LowState freshness observation (if enabled):
CPU/GPU/RAM/temperature/throttling observation:
start and stop confirmation for every manually launched workload:
result: PASS / FAIL / UNVERIFIED
notes:
```

## Stop and degradation policy

Stop the optional workload being evaluated before touching priority traffic:
raw cloud, decimated cloud, Dataset/model transfer, preview rate/profile, then
shadow inference. Never relax control or LowState safety checks to improve a
matrix result. After a disconnect, verify no auto-arm, no stale-result reuse,
one receiver generation and one producer before resuming the row.

## WP02 software-only evidence

The automated tests cover bounded windows, rate expiry, malformed health,
fixed-argv Wi-Fi probe behavior, timeout/missing metrics, receiver counters,
latest-only browser queue depth, decode failure recovery, stale presentation
and the explicit unverified cross-host clock label. Hardware rows remain
`UNVERIFIED` until the operator records them here.
