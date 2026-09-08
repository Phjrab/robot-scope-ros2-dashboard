# Track C4 new-map supervised goal preparation

Date: 2026-09-08

Status: `PREPARED_AWAITING_DEPLOYMENT_AND_NAV_SESSION_APPROVAL`

Motion status: `NOT_RUN`

This record prepares the new operator-selected map for the existing supervised
Track C4 sequence. It does not authorize a navigation session, navigation
lease, initial pose, goal, deadman, non-zero command, Mission, or robot motion.

## Repository and live identity

- Repository commit at preparation start:
  `3e0a9aa109cde1b90c31311e948ef49a5809b79a`.
- `main` and `origin/main` matched and the working tree was clean before this
  focused change.
- External dashboard symlink and process release:
  `5bf184d63247186faa23dc5197e1c21a470a7d41`.
- Signed robot-side Control Bridge release:
  `10a7fa9cec2c329f2c50edc9ad98de13a22689da`.
- No service, release symlink, map, navigation session, lease, or command was
  changed during this preparation.

The mixed deployed releases are recorded facts, not an accepted C4 release
pair. A clean exact release and rollback plan must be shown before deployment.

## New pinned route

| Item | Exact value |
| --- | --- |
| Map | `map_20260908_072712_edited` |
| Map ID | `8050fff44b44ce106dc5a210` |
| Map revision | `9e72787f2443b714ed3045fda62c08c53e85294c7d02e26b8e74ce0cc30fc8ac` |
| Map geometry | 295 x 205 at 0.05 m/cell |
| Map origin | `[-10.5254297256, -4.29361486435, 0.0]` |
| Start pose | `(0.00, 0.00, 0.00)` |
| Proposed goal | `(0.25, 0.00, 0.00)` |
| Direction and distance | straight forward `+X`, 0.250 m |
| Robot-radius corridor | 0.220 m radius |
| Stopping buffer | 0.150 m beyond the goal |
| Checked corridor | start through `x=0.40`, sampled every 0.01 m |
| Minimum occupied/unknown/map-boundary clearance | 0.793614864 m |
| Net clearance beyond robot radius | 0.573614864 m |

The route calculation decoded the exact revision-pinned occupancy payload.
Every non-free value, including unknown cells, was treated as an obstacle. The
calculation permits only the fixed 0.25 m straight goal; it does not prove the
physical floor is clear or that the robot is still at the proposed start pose.

## Live read-only preflight

The external dashboard was active and the robot target was reachable. The
signed Bridge was ready, authenticated, connected, and reported fresh
LowState. Graph cardinality was one owned Sport publisher, one Sport
subscriber, zero foreign named publishers, ten expected bare Unitree
publishers, and eleven total publishers. Battery was 90 percent in this
snapshot. The control lease was inactive, deadman was released, and both the
manager and accepted command were exact zero. Bridge request evidence showed
zero Move, non-zero Move, action, other, and active motion-run requests.

Navigation, localization-only, Mapping, and goal state were idle. The prior C3
initial-pose count remained historical evidence only and is not reusable in a
new normal navigation session.

## Focused checker change

`scripts/check_track_c4_navigation_ready.py` now accepts explicit `--map-id`
and `--map-revision` pins. Both values remain strict opaque hexadecimal
identities and are cross-checked against the live navigation session and the
downloaded map payload. The historical map remains the default for retained
runbooks, while a new map must be supplied explicitly.

The fixed start, 0.25 m goal, 0.15 m stopping buffer, 0.22 m robot radius,
35-percent speed scale, 0.30 m/s server clamp, C4 parameters, stabilized READY
dwell, odometry maximum gap, lifecycle, topic cardinality, TF, signed Bridge,
LowState, lease ownership, deadman, raw-command, watchdog, and exact-zero
requirements were not relaxed.

## Software validation

- Focused C2/C3/C4: 45 tests passed.
- Full Python repository suite: 1,369 tests passed.
- JavaScript unit suite: passed.
- Cockpit JavaScript suite: 94 tests passed.
- Playwright hardware-free browser suite: 36 tests passed.
- Ruff and `git diff --check`: passed.

The first Playwright invocation was blocked by the local sandbox from binding
its test port. The identical suite passed outside that restriction; this was
an environment failure, not a product-test failure.

## Next mandatory gates

1. Publish the focused commit and wait for CI.
2. Show the exact clean release, both-host compatibility, deployment order,
   and rollback release; obtain explicit deployment approval.
3. Reconfirm the robot is standing and completely stationary at
   `(0,0,0)`, facing the mapping-start direction, with at least 0.40 m of
   clear physical space ahead and a physical remote/E-stop in hand.
4. Obtain a new approval for one normal navigation no-goal session. Starting
   that session is allowed to acquire only the Navigation lease.
5. Show the exact map/revision/parameter revision again and obtain a separate
   initial-pose approval before publishing it exactly once.
6. Require stable C4 READY for at least 10 seconds with an idle goal and exact
   zero command, then stop and obtain a separate one-shot goal approval.

No prior C3, C4, C4A, C4B, or general approval can be reused for the motion
step. Any mismatch or loss of health requires reverse cleanup and a new
session; no goal may be retried automatically.
