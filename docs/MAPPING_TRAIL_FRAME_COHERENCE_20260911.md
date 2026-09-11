# Live mapping trail frame coherence

## Evidence and scope

The supplied screenshot shows a `hesai_lidar` cloud, a SENSOR EXTRINSIC /
ODOMETRY WAITING model, and a distant purple trail. Read-only pose inspection
returned stale `/Odometry`, frame `camera_init`, age 618.192 seconds, with null
position/orientation. Mapping control reported failed preview (relay offline)
and failed pipeline preflight. The operator subsequently confirmed the robot
was powered off. These current failures do not establish the sensor failure
cause at screenshot capture time.

## Confirmed rendering defect

`RobotScene3D._displayTrail()` previously interpreted a missing current pose as
no frame mismatch, returning the historical world-frame trail unmodified.
Meanwhile the robot model used the sensor extrinsic preview. A sensor extrinsic
does not supply a world-to-sensor transform. The 2D projection also drew pose
and trail without checking their frame against the cloud.

## Change

- 3D trails require a current pose and one explicit matching cloud frame.
- No guessed translation between coordinate frames is performed.
- 2D robot/trail overlays require the same frame checks.
- Invalid/stale pose clears application trail history; the existing sensor
  extrinsic preview and ODOMETRY WAITING label remain.
- Same-frame fresh trails continue to render. Mixed/unknown frames fail closed.

This is not an odometry recovery or a TF calibration. Timestamp guards, source
selection, mapping, control and navigation behavior are unchanged. No service
restart, deployment, mapping launch or motion was performed.

## Validation

JavaScript unit suite: 292 passed. Python unittest discovery in repository
virtualenv: PASS. Frontend syntax: 58 modules passed. Secret scan and
`git diff --check`: PASS. Added regression covers absent pose, sensor/world
mismatch, matching frame, mixed history and unknown frame.

After robot power-up, separately verify mapping state, fresh FAST-LIO output
and registered cloud/pose frame agreement. Deployment and live visual
verification remain pending; no claim is made that the displayed sensor
preview is a measured world position.

## Authorized external deployment and stationary input check

Following operator approval, deployed `d345c0f393fc54e3fe593fce21b01acedfe426c7`.
CI run 34572196991 passed both Ubuntu/Python matrices. Archive SHA-256:
`5a4b705fac0c1647ff4e9e77e355b9140c7d769639b7b3396bb6d557fce00afe`.

The first activation failed because the archive lacked the native D2 build.
Rolled back immediately to `fbe8cd0`, verified HTTP service recovery, then built
the exact-release registration core, CLI and PCL NDT2D backend. CTest passed
1/1. Re-activation succeeded: PID 276539, NRestarts=0, process cwd matched the
new release. scene3d.js SHA-256 matched local and deployed files:
`1db84155c330cb9227662e4541a1e0701b48ec604109413132fdb25cbdb6b264`.
Future archive deployments must prepare these native artifacts before activation.

Started the allowlisted mapping pipeline at 07:09:50 UTC. Raw cloud, IMU and
FAST-LIO readiness passed. Two pose snapshots approximately 31.6 seconds apart
advanced from seq 74 to 389, with ages 27ms and 13ms, both `ok`,
`camera_init -> body`. Raw cloud remained `/velodyne_points`, `hesai_lidar`,
8000 displayed / 16000 source points. Thus the raw cloud is not a world-frame
trajectory canvas even when odometry is fresh.

Control evidence: no lease, deadman false, accepted command exact zero,
Move count 0 and action count 0. Onboard Bridge release remained `10a7fa9`.
Stopped only the test mapping pipeline at 07:10:59 UTC (state stopped,
exit 130, no error). Preview remained running; no map saved, initial pose,
Navigation goal or motion requested. Odometry becoming stale after this
intentional stop is expected. Browser visual verification remains separate
from these API and deployed-file checks.
