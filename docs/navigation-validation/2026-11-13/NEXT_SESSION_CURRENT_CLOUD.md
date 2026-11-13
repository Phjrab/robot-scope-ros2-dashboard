# User-requested stop before current-cloud preservation

The user requested preservation of **current hardware input**, comparison with
the map, and failure analysis. They explicitly authorized necessary investigation
without repeated permission questions. They subsequently stopped the task to
turn off the robot and continue tomorrow. No further hardware action is authorized
by this record alone after a new boot; first read actual state and carry forward
the user's existing scope without inferring physical readiness.

## Last observations and incomplete capture

At 22:02:40 KST the actual API readback was:

- Release `8234fcdb3d79b69c8b942d9bb42bfc25e57b141c`.
- Observation `0c50a6c7526a4e6d8323a6237ecdcb52`, READY, active/busy true,
  signed guard HELD, owner_failure null.
- Control STOP=true, lease=false, bridge Move count=0.

The current browser showed the same map pair/generation
`8409e46836ba4920835367d4e81296d4`, and a newer draft:
X=4.6708120017651655, Y=3.429015474413666, yaw=-3.066965147882281.
The stationary checkbox was unchecked. These are historical UI values, not
permission to restore or confirm that draft on a new boot.

The UI retained a rejection received at 22:02:09.125 KST for proposal
`fcb00dd3a661e0fefb178842`, same observation session, reason PRIOR_NO_MATCH.
There were ten retained diagnostic entries, including duplicates; none matched
the prior. Their XY differences ranged approximately 10.50–11.89 m and yaw
differences approximately 3.02–3.13 rad. The agent did not issue that calculation.
Its actor and exact input bytes were not established in this resumed task.

A bounded input-preservation helper was prepared remotely under
`/home/unitree/robot-scope-diagnostics/current-cloud-20261113/capture_once.py`.
It was designed to copy `input.json`, `scan.f64`, `map.f64` from a new temporary
global-worker directory, verify sizes/hashes, and match the complete context to
one new session-bound diagnostic job. It would omit operator_prior rather than
inventing a current stationary acknowledgement.

**The helper failed its initial state assertion before starting its watcher or
sending any POST.** The assertion combined expected session ID, READY and HELD;
the failed condition was not disambiguated. Do not claim a proven session change.
It did not preserve current XYZ and did not run a new calculation. A subsequent
read-only status request produced no response; the SSH connection ended with
connection reset after the user's stop instruction.

Final physical power/STOP/lease/observation state is therefore **unconfirmed**.
The earlier READY/STOP-held sample is historical, not a shutdown confirmation.
No service restart, observation start/stop, new calculation POST, confirmation,
INITIAL POSE, Nav2, goal, STOP release or motion request was made in this attempt.

## Concrete lead to verify next

Repository code distinguishes generic `fastlio_xt16.yaml` from the opt-in
`fastlio_xt16_d2_relocalization.yaml`. Both have surface/map voxel size 0.5 m and
point_filter_num=1; dense_publish_en is false versus true. Current onboard
selection supports the D2 flag or explicit allowlisted filename. Observation
mode does not itself override dense publication or surface voxel size.

Historical inspected FAST-LIO source records explain that dense=false publishes
the surface-downsampled cloud. Exact-stamp inverse odometry cannot recover points
already discarded upstream. This is a plausible cause of limited query features,
**not a demonstrated cause of the current failure**. Effective live parameters
and point populations still need measurement. Do not enable dense publication,
switch modes, change thresholds or restart services based on this hypothesis.

References: `scripts/select_fastlio_query_config.sh`,
`tests/test_stationary_fastlio_config.py`, and
`docs/c0-field-validation/20261030/RETRY_STATIONARY_20261031.md`.
The dashboard extraction's source_points/sampling metadata must be distinguished
from upstream FAST-LIO thinning. Dense registered XYZ is processed sensor output,
not original raw LiDAR packets; 0.5 m voxel size is not a measured pose error.

Next one task after restart: read actual runtime/map/session/control state, then
preserve the exact current registered XYZ and map before one agreed diagnostic
calculation; record effective dense/surface-filter parameters and compare with
the preserved historical input. Keep original arrays unchanged and outside Git.

No executable code changed. Previous unchanged-code validation remains recorded
in PRIOR_SEEDED_TRIAL.md (JS29 pass; Windows full unittest failed with25 failures,
422 errors and22 skips; separate exact deployed Linux CI passed). This handoff
does not claim a new successful full suite or current-cloud comparison.
