# Shadow-perception result integration

## Contract and validation

Every lane, object and depth-summary result uses
`robot-scope.perception-result/v1` and carries source/boot/sequence identity,
robot-monotonic capture and inference timestamps, exact model ID/hash/backend,
input dimensions, status, confidence and a task payload. The external policy
is the sole allowlist for source ID, model identity, dimensions and object
class names. A remote payload cannot add or rename a class.

The external runtime rejects unknown schemas, sources, models or hashes;
non-finite numbers; unordered/out-of-frame boxes; more than 100 detections;
stale robot-relative timestamps; invalid boot/sequence changes; malformed or
oversized responses; and unexpected source IPs. Duplicate sequences are
counted but do not refresh freshness. Gaps are recorded. A boot-ID change
starts a new sequence epoch. Last-good results become `STALE` after two seconds
and are never kept `LIVE` through transport loss.

Read-only endpoints are separate:

- `/api/v1/perception/health`: transport and validation counters;
- `/api/v1/perception/latest`: one current projection per task;
- `/api/v1/perception/history?limit=N`: at most 120 validated entries.

History is an in-memory diagnostic window, not a dataset or unbounded log.
Dataset samples include only a bounded model/result reference, not the raw
payload. Restart begins at `WAITING`; the receiver never infers an active model
from old data.

## Dashboard behavior

The Sensors RealSense view and RealSense Cockpit panel use a separate overlay
canvas. They show lane geometry, bounded object boxes/class/confidence, model,
sequence, receive age, inferred FPS/latency, `LIVE`/`DEGRADED`/`STALE`/`OFFLINE`
state and an explicit `SHADOW`
badge. Stale geometry is redrawn gray/inactive with its age. Canvas content is
cleared before every projection and when no validated result remains. Go2's
built-in camera does not claim the RealSense inference overlay.

No perception module imports control/navigation code or calls a motion API.

## Deployment and hardware smoke plan

Hardware validation is `BLOCKED` until approved model artifacts and policy
hashes exist. Do not enable either service automatically. Under an approved,
stationary test with Controls DISARMED and Navigation STOPPED:

1. Record the dashboard, relay and sidecar enable/active states and current
   commit. Confirm the policy model hashes match robot-side manifests.
2. Install reviewed files without starting services. Keep the existing manual
   start policy.
3. Start the RealSense relay and shadow sidecar manually; do not start control,
   mapping or navigation.
4. From the external Orin, verify health/latest/history, SHADOW overlays, exact
   source IP, model hashes, sequence advance, input age and gray stale cleanup.
5. Stop/restart only the sidecar to verify OFFLINE/STALE to LIVE recovery,
   duplicate suppression and boot/sequence behavior. Do not disconnect the
   robot network during an unsupervised test.
6. Record FPS/latency/temperature and relay viewer/producer counts. Stop the
   sidecar and restore the recorded service states.

Passing unit/E2E tests does not remove the hardware `BLOCKED` gate.

## Rollback

First remove the three dashboard environment values
`ROBOT_SCOPE_PERCEPTION_SOURCE_IP`, `ROBOT_SCOPE_PERCEPTION_RESULT_PORT` and
`ROBOT_SCOPE_PERCEPTION_POLICY`; the dashboard then has no receiver owner or
perception routes with live data. Stop only the manually started sidecar and
confirm the RealSense relay retains its previous state. Restore the previous
sidecar script/env and dashboard commit from recorded copies if required.
Never delete model artifacts, datasets or maps as part of WP04 rollback, and
never change control-bridge configuration.
