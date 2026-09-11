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
