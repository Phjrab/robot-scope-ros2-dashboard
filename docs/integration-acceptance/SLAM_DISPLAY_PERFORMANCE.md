# SLAM display performance — 2026-10-16

The user reported choppy mapping display and authorized software optimization.
They confirmed the robot is powered OFF. Device observation remains deferred:
no SSH/device probe, deployment, service restart, camera session, movement or
operating ROS change occurred. The source base is `4bf1ec4`; implementation and
test file hashes are in [SLAM_DISPLAY_PERFORMANCE.json](SLAM_DISPLAY_PERFORMANCE.json).
The previous native candidate3986a75 remains undeployed. Any future deployment
must prepare and validate the new source, not reuse that older bundle as though
it included this optimization.

## Evidence and diagnosis

Read-only analysis of the preserved manual01 collector found230 active samples
over162.2s: approximately1.41 received snapshots/s, median interval0.716s,
p95 1.254s. Median interval was0.281s before a global map was present and1.028s
with at least8000 points. This association is not a causal CPU profile.
The retained final full sample is963089 JSON bytes, with13993 global points
occupying839736 bytes (87.2%). The compact websocket.jsonl omits media and point
arrays; its row sizes cannot establish wire traffic. These observations are
collector cadence, not camera FPS, browser FPS or sensor-to-display latency.

The code repeatedly copied unused cloud/path caches, serialized geometry while
holding sensor callback locks, sent complete unchanged geometry and rebuilt
browser geometry on every frame. It also cleared the image canvas before each
decode, causing blank intervals while replacement pixels were loading.

## Changes

- `SlamGeometryTransport` supports the explicit WebSocket query
  `geometry_updates=1`. Each connection keeps at most one complete global map
  and one trajectory. Initial/changed layers are sent in full. An exactly equal
  layer is referenced by a connection-local token. The whole layer is compared;
  count, timestamp or snapshot ID alone cannot suppress a geometry correction.
  Source metadata, native map data and export paths are unchanged.
- Legacy clients still receive full frames. The browser hydrates references
  only within engine/session/generation/epoch/frame context. Invalid references
  hide only that layer. Connection or session changes reset caches; a session
  readback change reconnects to recover a full frame that might have arrived
  before the readback. Images, pose and tracking remain independent.
- Source sampling and final WebSocket JSON serialization run in a worker thread.
  Feature capture stays atomic with image-history selection, but detached
  wire-budget serialization runs outside both feature and runtime callback
  locks. Runtime copies only the image and pose it consumes. Nested trajectory
  points are detached before releasing the lock. Lifecycle checks remain.
- The browser retains one pending animation-frame update and one active image
  decoder with one latest pending image. Intermediate display work is replaced,
  not accumulated. Exact repeated pixels can reuse the decoded image; actual
  pose values are not interpolated. Valid old pixels remain during decode only
  within their original receipt-age guard. Disallowed overlays are removed
  immediately, including tracking loss or operator toggle during slow decoding.
- Unchanged point geometry avoids conversion/sorting/static-layer rebuilding.
  Camera mode changes are applied only when the mode changes. A changed point
  coordinate still rebuilds the geometry even with the same count/stamp/ID.

The existing1s source freshness,5ms stereo pairing,20ms overlay alignment,
1500ms browser receipt guard, wire limits and1s WebSocket send timeout remain.
Operational DDS, camera calibration, estimator inputs, TF and policy enforcement
were not changed. This optimization does not fix the reported duplicated walls
or qualify SLAM geometry accuracy.

## Verification

Full Python:2165 total,2163 passed/2 skipped (80.567s). JS:393 passed, with the
22 SLAM unit checks rerun after the final frontend fixes. Browser fixtures:20
SLAM checks passed after final fixes, plus10 presentation checks in the earlier
combined28-check run. The final stream tests cover actual canvas pixels during
delayed decode, geometry references, unavailable layers, session readback races,
reconnect, stop/save and multiple tabs. Unchanged-map repaint also verifies zero
additional point-cloud rebuilds. These are hardware-free checks.

Ruff, configured mypy (four configured modules), tracked-secret scan,84-module
frontend syntax and diff checks passed. Independent review identified and closed
the delayed-overlay and context-reseed issues. The initial sandboxed full Python
run encountered24 local socket permission errors, and the first browser attempt
could not bind127.0.0.1; those failed environment attempts are retained and excluded
from acceptance. Local socket-enabled verification then passed without device access.

A repeat-delivery microbenchmark replays the preserved final real sample once
then50 times with new transport sequence numbers. It deliberately freezes the
sample and is not a reconstruction of missing full records. Uncompressed repeat
messages fell from963087 to62174 bytes (**93.54% reduction**); initial referenced
delivery is963213 bytes. Local median repeat encoding time was16.005ms versus
0.532ms on macOS/Python3.13.2. The numbers exclude upstream feature assembly,
broker JSON, networking and browser drawing. They do not predict robot FPS or
end-to-end speedup. Image, pose, overlay, observations and readiness compared
exactly to the source sample; the private input hash was unchanged.

Private scripts, replay output, review/test logs and original failed attempts:
`robot-scope-hardware-validation-private/slam-display-performance-20261016/`.
No map/media or private evidence was added to Git.

## Remaining minimum runtime check

After a new user request and current field confirmation, prepare the latest
candidate, preserve runtime/config/UI ownership and deploy separately. One
bounded stationary observation should measure source receipt/capture/encode,
broker round trip, WebSocket arrival, browser decode/draw and fresh-channel
availability independently. Inspect the negotiated references and compare first
and unchanged-map messages. Leave sensor-to-browser latency unknown unless clocks
are related. Upstream broker geometry serialization and sensor/native processing
remain potential costs; profile them before changing rates or adding compression.
No device run or background continuation is scheduled. Bridge restoration and
driving remain excluded.
