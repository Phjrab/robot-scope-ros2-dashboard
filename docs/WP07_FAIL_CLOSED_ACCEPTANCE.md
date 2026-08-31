# WP07 fail-closed acceptance and fault recording

## Scope

WP07 extends the existing read-only acceptance recorder for the distributed
RealSense and shadow-perception topology. The recorder performs bounded GET
requests only to fixed loopback dashboard endpoints and runs only the existing
fixed `git rev-parse HEAD` and `systemctl show` argument vectors. It never
disconnects Wi-Fi, stalls a source, restarts or stops a process, changes a model
or PointCloud setting, acquires a camera viewer, publishes ROS data, or sends a
robot command.

The robot was deliberately powered off during the initial repository
implementation, so its hardware-free tests proved classification and recorder
safety only; none are inferred as `PASS` for that hardware-free run. A later
robot-connected follow-up is recorded below; supervised rows still remain
`NOT_RUN` unless all five field confirmations are explicitly provided to the
recorder.

## Read-only observation contract

The report records the deployed commit, dashboard identity, private robot-side
camera/perception source identity, configured ROS interface, RealSense source
and receiver metrics, Wi-Fi metrics, perception state and result age, model
IDs/hashes, clock-domain status, Dataset reserve, Competition Lock, existing
control/LowState/cardinality, and PointCloud mode/budget.

| Check | PASS boundary | Fail-closed classification |
|---|---|---|
| Go2 link | `go2-control` requires a fresh authenticated signed Bridge/LowState link; Nav/XT16 modes still require their direct ROS interface | missing mode-required link is `BLOCKED` when the agent remains observable; a missing required ROS interface in a direct-ROS mode is `FAIL` |
| RealSense source/receiver | at least 10 Hz and age at most 3 s | offline/missing hardware `BLOCKED`; explicit stale or inconsistent live state `FAIL` |
| Perception result | `LIVE` only at age at most 2 s | older/frozen/disconnected result must be `STALE`; old result labelled `LIVE` is `FAIL` |
| Model identity | runtime task ID and backend artifact SHA-256 match the local active ONNX/engine record | mismatch is `FAIL`; absent active/runtime evidence is `BLOCKED` |
| Compute | CPU/GPU/RAM/temperature/throttling available together | missing set `BLOCKED`; malformed set or throttling `FAIL` |
| Network interval | RTT p50/p95/p99, loss and minimum observed throughput available together | incomplete set `BLOCKED`; one link rate or ping cannot pass |
| Competition | Lock enabled, non-physical, authority `NONE`; mode MANUAL/SHADOW/SAFE_STOP | unlocked, AUTO/ASSISTED or non-zero authority is `FAIL` |
| PointCloud | robot-side `OFF`/fresh `SUMMARY`; dashboard diagnostic at most 60,000 points | raw is `BLOCKED` pending supervision; oversized/malformed budget is `FAIL` |

These thresholds are acceptance-only constants. WP07 does not change any
runtime timeout, speed limit, graph cardinality rule, lease rule, Dataset
reserve, or navigation freshness gate.

## Fixed supervised scenarios

WP07 adds these fixed IDs:

- `supervised.robot_wifi_disconnect`
- `supervised.realsense_source_stall`
- `supervised.realsense_relay_restart`
- `supervised.perception_process_stop`
- `supervised.perception_result_freeze`
- `supervised.model_hash_mismatch`
- `supervised.model_activation_rollback`
- `supervised.preview_consumer_disconnect`
- `supervised.decimated_pointcloud_load`
- `supervised.raw_pointcloud_overload_abort`
- `supervised.dashboard_receiver_restart`
- `supervised.competition_lock_mutation_rejection`

Exactly one scenario and one literal result (`PASS`, `FAIL`, `BLOCKED`, or
`NOT_RUN`) are accepted per invocation. Repeated selectors are rejected instead
of silently taking the last value. Every supervised record retains all five
operator confirmations. There is no free-form evidence, URL, endpoint, unit,
topic, executable, command or output argument.

## Expected fault behavior

- Wi-Fi/receiver loss makes camera and perception stale or offline. Reconnect
  creates no automatic ARM, AUTO resume, lease or motion authority.
- A source stall cannot present the last image as live. Dependent AI results are
  stale and Dataset publication must not publish an incomplete sample.
- A perception stop/freeze removes readiness but does not affect or bypass the
  signed control bridge.
- A model mismatch leaves the old active and previous records intact. Activation
  and rollback remain explicit local operator actions.
- Preview disconnect releases its single demand owner. Receiver or relay restart
  must not create duplicate consumers or producers.
- Optional PointCloud traffic is reduced or aborted before control, LowState,
  result or preview freshness rules are touched. Raw overload is never accepted
  as `PASS` merely because the stream continued.
- Competition Lock rejects configuration mutation while STOP, DISARM, bridge
  stop, navigation cancellation, mission abort, mapping stop and Dataset
  finalization remain available.

## Field procedure

Do not run a supervised scenario while the robot is powered off. For a later
explicitly approved field session:

1. Deploy and record one exact Git commit on both reviewed hosts.
2. Confirm the clear area, present safety operator, physical remote/E-stop,
   low-speed limits, stationary robot, DISARMED state and no unexpected lease.
3. Run the read-only recorder and retain the private JSON/Markdown pair.
4. Select one fixed scenario. Perform only its approved external procedure; the
   recorder does not create the fault.
5. Stop immediately on unexpected motion, failed deadman/stop, stale data shown
   live, priority-traffic degradation, restart loop, OOM, throttling or reserve
   violation.
6. Return to stationary/DISARMED, record exactly one result, then inspect before
   considering another invocation.

The physical remote/E-stop always has priority. Dashboard SOFTWARE STOP and
Competition Lock are not physical safety devices.

## Current hardware status

On 2026-08-31 the external Orin ran commit `758e274` in `go2-control` mode while
the robot was powered and stationary. Competition Lock was enabled only for the
read-only collection, then explicitly released. The private report summary was
`PASS=27 FAIL=0 BLOCKED=22 NOT_RUN=24`. The fresh authenticated signed Bridge,
LowState freshness/cardinality, exact split-topology link contract, dashboard
identity, Dataset reserve and non-physical zero-authority Lock were observed;
no ARM, lease, deadman or non-zero command was created.

The following remain intentionally `BLOCKED` or `NOT_RUN` for WP07:

- robot-side Wi-Fi RSSI/link and full RTT/loss/throughput interval;
- RealSense source-stall/cable fault behavior and the formal supervised relay
  scenario record; live source/transport and immediate relay restart recovery
  were observed separately at `f48ef07` without promoting the scenario row;
- live shadow perception, model match, task ages and complete compute metrics;
- robot-side PointCloud mode and coexistence with live optional workloads;
- direct external ROS, XT16/FAST-LIO and Navigation evidence, which is outside
  the accepted split `go2-control` link and remains required in Nav/XT16 modes;
- every formal supervised scenario, because the five recorder confirmations
  were not supplied; separate dashboard-restart and Lock-rejection observations
  and the 2026-08-31 preview demand disconnect/reconnect observation were
  deliberately not promoted to supervised `PASS` records;
- physical no-auto-resume and bounded-stop observations.

## Rollback

Revert the WP07 commit to remove the additional recorder checks and scenario
catalog. Existing runtime reports are immutable private evidence and should not
be deleted or edited. A later dashboard restart is a separate supervised
lifecycle action; reverting repository code does not authorize it. The pre-WP07
control, mapping, navigation, model, Dataset and filesystem behavior is unchanged.

## WP08 gate

Repository-side WP07 completion permits release-document preparation, but it
does not authorize an operational release. WP08 must preserve every field row
above as `BLOCKED`/`NOT_RUN` until an explicitly approved robot-connected run
records the evidence at the exact release commit.
