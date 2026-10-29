# Insertable frontend contract

```js
import {mount, createRobotSceneRenderer} from './features/multimap_fusion/index.js';
const instance = mount(host, {
  catalogue, // async list() -> {schema,sources}; preview(source) -> pinned sample
  jobs,      // async start(request), get(jobId), cancel(jobId), accept(review), save(export)
  renderer: createRobotSceneRenderer(window.RobotScene3D),
  onReview: acknowledgement => {},
  confirmDiscard: () => window.confirm('Discard UI draft?'),
  pollMs: 350,
});
await instance.ready;
instance.snapshot(); // detached UI state; no server mutation
instance.destroy(); // listeners/timers/renderer cleanup; late results ignored
```

Import starts no process, worker, model, ROS client or network connection. The
module only accesses its host and injected ports; there is no product entrypoint.
`createHttpPorts` is the C2 fixture-contract transport adapter; `createC1Ports`
(in `c1_ports.js`) translates the separately published C1 v0.1 HTTP contract.
All paths are centralized and confined to the multimap extension.

C2 schema: `robot-scope.multimap-ui.v1`. A UI source has `id,name,kind:'pointcloud3d',
session_id,revision,sha256,frame_id,units:'m',point_count,axes_verified,ancestors`.
An optional `wire_descriptor` retains the full unchanged C1 source for transport.
Source IDs, session IDs, revisions and content hashes are pinned independently.
Preview arrays are sampled/temporary and limited to 6,000 retained XYZ points per
source, at most eight sources. Merged 3D rendering is capped at 12,000 points.

Requests carry source descriptors, anchor, row-major 16-value initial guesses,
XYZ correspondence pairs, draft revision and pins. Points obey
`p_fused=T_fused_source@p_source`, column vectors, meters and radians. Matrix
validation rejects scale, reflection and non-finite values. This is geometry
validation, not registration. Each session's origin is independent.

Every manual edit, source/anchor edit, undo, redo and reset increments the draft
revision and invalidates the server candidate. Undo/redo restores only UI draft
history. A request ticket includes a nonce and draft revision; replies also check
input pins, job ID, increasing job revision and immutable proposal revision.
Late replies cannot replace a newer manual prior. Drag shows a gesture overlay,
and commits a single history entry on release. Review/save temporarily disables
draft editing so a confirmed persistence operation cannot lose its ownership.

Response states include RUNNING, SOLVED_CANDIDATE, NEEDS_PRIOR, DISCONNECTED,
REJECTED, FAILED and CANCELLED. Diagnostic terminal proposals remain visible.
Accepted/rejected edges, components, metrics and ambiguity warnings are retained.
Disconnected candidates cannot be accepted. Low RMSE does not imply success.
The user must explicitly acknowledge warnings and accept a current candidate;
server review acknowledgement precedes export. C1's increased review revision
is checked against the reviewed candidate revision, then used for export.

Export sends a name/proposal/review identity/pins only, never preview arrays.
Success requires a new ID/revision/hash and a false runtime-installation flag.
Original source selection remains unchanged; catalogue refresh failure does not
turn the saved artifact into a missing or active map. C1's unregistered export is
reported as saved with catalogue registration pending. Derived 2D cells are only
shown when supplied; missing/unsupported data stays unknown, never free space.

3D correspondences are explicit XYZ triples or actual sampled XYZ picks. A
projection pixel never supplies an inferred Z. Fewer than three, collinear,
clustered or duplicate pairs fail validation; a fourth distributed pair is
recommended. Groups are checked independently per source before a job request.

The synthetic fixture simulates state and transforms. Only the explicitly
classified exact C1/D1 synthetic test executes D1's solver. Neither qualifies as
REPLAY_REAL, NATIVE_NAV2_SIM, product integration, deployment or device evidence.
