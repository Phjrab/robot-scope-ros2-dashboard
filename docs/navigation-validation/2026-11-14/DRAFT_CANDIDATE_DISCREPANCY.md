# Why the frozen dense fit moved 1.409 m from the draft

Date: 2026-11-14, Asia/Seoul. Follow-up to
[current cloud comparison](CURRENT_CLOUD_COMPARISON.md).

## Conclusion and evidence boundary

The **1.409103 m** is the distance between the last recorded UI draft
`(4.670812, 3.429015)` and the unaccepted offline dense fit
`(3.934890, 4.630677)`. It is **not a measured robot-position error**.
The correction is `(-0.735922, +1.201661) m` in map XY.

The geometric reason is reproducible: at the draft, two substantial scan planes
do not overlap the corresponding map-wall hypotheses. The fitted translation
almost removes their range discrepancies. Independent extraction here means
separate extraction from map and scan; it is **not independent physical evidence**
because this is the same scan used for the fit.

The operator now reports the chair behind the robot and wall distances
"220 230 정도", interpreted provisionally as roughly 2.2 and 2.3 m. A subsequent
clarification specifies **body centre to the outermost physical walls**. Wall
order, measurement method and body-centre-to-IMU offset remain unconfirmed. Neither the
draft nor the candidate exactly agrees with those rough ranges. Therefore this
investigation does not establish which pose is physically correct or adopt a pose.

## Frozen inputs and map agreement

Same preserved stamp: `1794633990863503694`. Dense scan has 15,358 original rows;
map has 32,387 rows. Original scoring retains duplicate scan rows.

- Scan SHA256: `187c8b77d1a196cc85bbe32ff1f7e457e57f38dd1815a2bf8c2e6145217af502`.
- Map SHA256: `5faf3f82b91150b2e4bd0b2ff8ab726ded8d0eba3c3ed056981d2b02a1f904dd`.
- Current 2D map: `map_20261113_181538_edited`, revision
  `f7fe51817b9201a775b66092e12644f47a8831ff40a12a43c82c86ec0953860e`.
- 3D map: `map_20261113_181538`, revision
  `67df671eb06987fec3ba189aa0c369718de6d228b469bbc205c4a5e9a7a0e84e`.
- Current pair generation: `740dcf3f09a145579791a2f286b5f326`.

Read-only `/saved-maps/{id}/data` returned a 300 x 181 grid, resolution 0.05 m,
origin `[-8.47166252136, -2.4770026207, 0]`. All **4,541 occupied cells** contain
at least one original 3D map point projected directly into the same XY cell:
100% coverage, zero missing occupied cells. Occupied-cell centre to nearest 3D
XY distance is median 0.01299 m, p95 0.02649 m, maximum 0.03421 m; all below
the 0.03536 m cell half-diagonal. This strongly rejects a uniform 1.409 m
stored 3D-to-2D offset, but does not establish correspondence to the physical room.

After the outermost-wall clarification, the current family API was read. It links
this exact 3D revision to this exact 2D revision using `planar_xy_identity`,
height slice **-0.2 to +0.8 m**, 0.1 m XY density bins and a minimum of 10 points
across the 3 x 3 neighbouring bins (`noise_radius=0.1`; not an exact radial test).
Offline replay of the production pure projection/pixel functions on preserved
points reproduces 300 x 181 and the origin within 3e-12 m. All 4,541 occupied
cells are identical. The only difference is 49,759 UNKNOWN cells changed to FREE.
Thus no effective crop or occupied-wall removal occurred relative to that
conversion. The 2D footprint still does not represent every height or every
physical outer wall: 32,387 source points become 14,422 after height filtering
and 13,179 after density filtering. This distinction matters when identifying
which physical surface a displayed boundary represents.

Stored calibration's navigation-map and IMU-to-base transforms are identity.
Its base origin is an existing approximate convention, not a new body-centre
survey. The configured 0.25 m LiDAR extrinsic is already incorporated in the
preserved FASTLIO body-frame cloud; it must not be added again.

## Plane ranges explain the numerical preference

Distances below are perpendicular distances from the IMU origin to infinite
planes, not body-edge clearance. Map/body plane identities are hypotheses.

| Plane hypothesis | At last draft | At dense fit | Extracted directly in body scan |
| --- | ---: | ---: | ---: |
| Upper boundary | 2.770 m | 1.494 m | 1.496 m |
| Outer right boundary | 1.383 m | 1.970 m | 1.974 m |

At the draft, discrepancies are 1.274 m and 0.590 m; at the fit they are
0.002 m and 0.003 m. Deterministic RANSAC/TLS extraction within 5 m uses unique
coordinates only for geometric support, leaving input arrays and scores intact.
The main body planes have 1,408 / 813 unique supporting points, plane-fit RMS
0.0082 / 0.0086 m. Solving XY from those two ranges and the proposed map walls
gives approximately `(3.935, 4.629)` using the recorded seed height. Using fitted
height instead barely changes this result. This is a conditional geometry check.

Full-cloud extraction also found these surfaces. The 1.496 m plane's largest
connected support spans approximately 6.64 m by 1.17 m (1,128 points); it is
not explained by one small chair alone. It remains unclassified without matching
the physical wall. No strong extracted plane at 2.2 or 2.3 m was found. In the
corresponding body-side directions, +/-0.10 m slabs at either reported distance
contain no points. This cannot distinguish occlusion, a different wall/direction,
an approximate measurement, sensor geometry, or an incorrect wall association.

The outermost-wall follow-up also removed all previous map ROI/height limits.
Only 103 / 53 / 25 of 32,387 map points lie more than 0.1 / 0.3 / 0.7 m beyond
the selected upper plane; corresponding right-plane counts are 34 / 28 / 20.
Farther 0.1 m projection bins contain at most 29 upper / 5 right points, with no
additional broad parallel wall identified. In the full body scan only seven
unique points lie over 0.1 m beyond the upper plane (all below the IMU); none
lie over 0.1 m beyond the right plane at any height. These are near the outer
envelope of **observed supported structures**, not proven building outer walls.
An opaque internal partition could hide the outer wall from LiDAR. Treating a
displayed boundary as the physical outer wall is therefore an unresolved
correspondence hypothesis, not an established operator error or sensor fault.

If 2.2 / 2.3 m are assigned to these same upper/right planes and the IMU origin,
the conditional XY is `(3.691, 3.893)`, 0.777 m from the fit. Swapping their order
gives `(3.802, 3.805)`, 0.836 m from the fit. These are illustrations of the
unresolved discrepancy, **not new initialization values**.

## Height/tilt and UI alternatives checked

Offline fixed-XY ICP optimizes only height and orientation, starting separately
from the recorded seed and fitted rotations/heights. It preserves all original
15,358 rows. Both runs converge to the same local result without hitting bounds.

| Frozen dense-cloud condition | Full nearest-map RMSE |
| --- | ---: |
| Recorded draft with old, unverified Z/roll/pitch | 0.568265 m |
| Draft XY with fitted height/orientation | 0.573925 m |
| Draft XY fixed; height/orientation optimized | 0.372456 m |
| Existing free-XY dense fit | 0.058414 m |

Thus tested height/tilt alternatives do not explain away the XY mismatch.
Nonconvex local searches are not a proof of the globally best transform or of
physical localization. The free-XY fit still exceeds the existing 0.05 m RMSE
gate and is 1.409 m from a prior whose existing position limit is 0.25 m.
No gate, timeout, source, or ownership condition was changed.

UI audit found consistent origin/yaw, resolution, Y reversal and canvas/CSS
scaling in `static/navigation.js`, `features/navigation/pose_draft.js`, and
`static/app.js`. Full draft precision is forwarded by `preparation.js`.
Relevant JS tests passed 25/25. Current browser backing/DOM dimensions both
read 516 x 550. Current UI has **no draft**, so the historical marker/click cannot
be verified now. Theoretical marker separation at this layout is 43.14 pixels.
No observed evidence supports a DPR bug or a resize during the historical drag.

## Execution, validation and preservation

This follow-up made read-only robot/API/browser requests and offline computations.
Observation start/stop, calculation API, proposal confirmation, INITIAL POSE,
operational registration, Nav2, goals, STOP release and movement requests: **0**.
No production code/configuration or deployment/restart was changed.

Readback around 14:50 KST: STOP=true, lease=false, bridge Move=0;
observation STOPPED, active=false, busy=false, guard=null. Actual service PID 995,
NRestarts=0, cwd release
`8234fcdb3d79b69c8b942d9bb42bfc25e57b141c`; same boot as the capture.
No seed or initialization handoff was adopted. Existing focus-preservation fix
therefore remains deployed; this documentation does not constitute a new deployment.

Required Windows full unittest: **1,798 tests, 24 failures, 421 errors, 22 skips**,
29.077 seconds, not a pass. The first sandboxed attempt stalled early and was
interrupted; the completed run used normal Windows permissions. Platform-specific
Unix API failures are present; no claim is made that every failure was individually
classified. Navigation/draft JS: **25 passed**. Exact published-commit CI is
reported separately from these local results and from hardware acceptance.

Evidence and helper scripts remain outside Git under
`../nav2-live-analysis-20261114/`: `current-wall-ranges.json`,
`current-two-wall-location-sensitivity.json`, `current-full-body-planes.json`,
`body-plane-connected-support.json`, `rough-distance-support-audit.json`,
`rough-wall-distance-hypotheses.json`, `rough-wall-distance-hypotheses.png`,
`current-fixed-xy-sensitivity.json`, `current-map2d-map3d-alignment.json`,
`current-map-projection-footprint.json`, `current-2d-map-data.json`,
`current-2d-metadata.json`, `current-2d-family.json`, `discrepancy-*.json` and test logs. Raw input hashes
were checked and originals preserved. No raw map/cloud or map image is committed.

Next one task: identify the two LiDAR-visible surfaces relative to the user's
outermost walls, accounting for the body-centre/IMU reference, then compare with
the preserved body cloud's 1.496 / 1.974 m surfaces. Do not auto-recalculate or apply a candidate merely
because its point-to-map residual is low.
