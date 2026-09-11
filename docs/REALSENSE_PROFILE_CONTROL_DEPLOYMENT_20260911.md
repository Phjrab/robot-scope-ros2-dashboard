# RealSense Profile Control Deployment — 2026-09-11

## Scope

The Sensors-page RealSense resolution selector was deployed without changing
robot motion, Navigation, localization, map data, Dataset capture, or the
onboard Control Bridge release. The selector is restricted to `320x240`,
`640x480`, and `1280x720`; it cannot accept a host, port, path, service name,
FPS, JPEG quality, or arbitrary command from the browser.

## Repository and CI

- Feature commit: `c4c0882c22d6cf0815d4d48e7df1aa592b440df7`
- Deployed external release: `1e22182c509aceb3e7a0a71274c885701707b6bc`
- The later release includes the already-published Route Planner responsive
  containment fix and the operational helper-path documentation correction.
- GitHub Actions run `34559317039` passed both supported matrices for the
  feature commit.
- GitHub Actions for `1e22182c509aceb3e7a0a71274c885701707b6bc`
  passed both supported matrices before activation.
- Exact `1e22182` archive SHA-256:
  `cfc6878697d90b657e2c4b95583aade17a1fc7747276a90a3a83263f332c7ae2`.

## Onboard Jetson installation

Target: `unitree@192.168.50.30`.

The existing forced-key target
`/usr/local/libexec/robot-scope/wireless-mapping-lifecycle-ssh` was backed up
and atomically replaced by the reviewed helper. The installed helper SHA-256
is `a5940f93a90b8f901db63def9109ba40a87b4cf9bedd94b21e122a7b6f92d94a`.
The exact sudoers policy was syntax-checked before and after atomic install.
It grants only fixed `start` and `stop` commands for the RealSense camera
service in addition to the existing fixed observation-service commands.

No onboard release pointer was changed. The Control Bridge remained on
`10a7fa9cec2c329f2c50edc9ad98de13a22689da`. The RealSense camera service
remained active with PID `2046`; no profile-apply request was sent during
deployment. Its profile therefore remained `640x480`, 15 FPS, JPEG quality
72. The Control Bridge remained active and its post-deployment signed status
reported no lease, deadman released, manager command exact zero, accepted
command exact zero, Move count zero, nonzero Move count zero, and action count
zero for the current bridge process.

Rollback copies:

- `/usr/local/libexec/robot-scope/wireless-mapping-lifecycle-ssh.pre-c4c0882`
- `/etc/sudoers.d/.robot-scope-wireless-mapping-remote.pre-c4c0882`

## External Jetson activation

Target: `jetson_orin_nano@192.168.50.10`.

The verified archive was extracted to
`/home/jetson_orin_nano/releases/robot-scope/1e22182c509aceb3e7a0a71274c885701707b6bc`.
The unchanged native registration build was preserved from the immediately
preceding `c1123be` release. Staged RealSense tests passed 8/8. The private
dashboard environment was updated with
`ROBOT_SCOPE_REALSENSE_PROFILE_CONTROL_ENABLED=1`, and the production symlink
was atomically switched. The shared lifecycle API reported no blockers and
scheduled the dashboard-only restart.

Post-activation evidence:

- `robot-scope.service`: active, PID `165872`, `NRestarts=0`;
- process cwd and production symlink both resolve to exact release `1e22182`;
- dashboard listens on `0.0.0.0:8088` and the loopback health endpoint passes;
- profile API is enabled, configured, available, and reports `can_apply=true`;
- profile API reports the active onboard relay as `640x480`, 15 FPS, Q72,
  `active/running`;
- Dataset capture is idle;
- Mapping pipeline and save operation are idle; only the configured persistent
  XT16 preview owner is running;
- Navigation, localization session, and goal are idle;
- no initial pose, goal, deadman, lease, or nonzero command was created.

Rollback state:

- release pointer: `/home/jetson_orin_nano/robot-scope.pre-c4c0882`, resolving
  to `c1123bef408ccb87168f64a3c91d29a12d023ac9`;
- private environment backup:
  `/home/jetson_orin_nano/.config/robot-scope/control.env.pre-c4c0882`.

## Operator behavior

The deployed control is available on the Sensors page. Selecting a different
resolution and confirming it changes only the two allowlisted width/height
assignments and cycles only `robot-scope-realsense-camera.service`. Dataset
capture blocks the mutation. A failed transition restores the original private
environment file and reports failure. Service enable/disable policy is not
changed.

## Follow-up selector-state deployment

Feature commit `fbe8cd0bb4960b1aa7f96103d81a2a7b27b56174` fixes a
browser-only state bug where the five-second profile poll replaced an
operator's pending resolution selection with the currently active server
profile before **Apply** could be used. The server allowlist, confirmation,
Dataset capture blocker, rollback behavior, and camera-service lifecycle
boundary are unchanged.

GitHub Actions run `34566718623` passed both supported matrices for the exact
feature commit. Its deployment archive had SHA-256
`11e7fcf16a9209f49e475397a91940f31a725d51c3f6605d7f318e0a26dcfdd6`.
The external release was staged at
`/home/jetson_orin_nano/releases/robot-scope/fbe8cd0bb4960b1aa7f96103d81a2a7b27b56174`;
the staged Python profile suite passed 8/8 and Python byte compilation passed.
The deployed selector file SHA-256 is
`13704ce295c8285a7283f9e4a33546c491109db7b10629013d11654bd7be35ec`.

The pre-restart check found an operator Dataset capture in progress. No stop
request was sent. Activation waited for its natural completion at 212 samples
and 26,064,528 bytes before invoking the dashboard lifecycle restart. No
resolution apply request was sent.

Post-activation evidence:

- production symlink and process cwd both resolve to exact release `fbe8cd0`;
- `robot-scope.service` is active with PID `228881`, `NRestarts=0`, listening
  on `0.0.0.0:8088`;
- rollback symlink `robot-scope.pre-fbe8cd0` resolves to `1e22182`;
- the profile API remains at `640x480`, 15 FPS, Q72 and reports no blocker with
  `can_apply=true`;
- onboard RealSense relay PID `1277` and Control Bridge PID `2264` remained
  unchanged across the external dashboard restart, both with `NRestarts=0`;
- Control has no lease, deadman is released, accepted command is exact zero,
  and Bridge request evidence reports zero Move, nonzero Move, and action
  requests for the running Bridge process;
- Navigation, localization session, and goal remain idle; no initial pose,
  goal, or motion command was issued;
- Mapping pipeline and operation remain idle; the configured persistent
  point-cloud preview owner resumed with the dashboard.
