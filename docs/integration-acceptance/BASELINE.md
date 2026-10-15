# Stage30 baseline — 2026-10-15 KST

> Current scope through40: the user explicitly extended the completed stage36 snapshot. Candidate863682e was deployed; initialpose1 and180s stationary observation were completed and owned resources cleaned. Live acceptance remains partial/false. See [STAGE40_VALIDATION.json](STAGE40_VALIDATION.json), [DEPLOYMENT_ACCEPTANCE.md](DEPLOYMENT_ACCEPTANCE.md) and [LOCALIZATION_LIVE_ACCEPTANCE.md](LOCALIZATION_LIVE_ACCEPTANCE.md). Earlier stop-after36/no-deployment statements below describe the historical software snapshot.41–43 remain NOT_RUN.

Main and fetched origin/main were clean at `2555f3763996c7b331389924bb5df48d62094736`.
GitHub Actions38695600100 completed success at2026-10-15T07:05:37Z.
MS implementation72641da/portability d866a3b and MR implementation22c7913,
MR evidence b42b28f and final2555f37 were read as sequential published history.
Earlier MS 'MR uncommitted' ownership text is superseded by those MR commits.
No reset/clean/stash, branch/worktree/PR, data migration or installation occurred.

The mentioned standalone `robot_scope_integration_followup_new_chat.md` is absent
from the supplied directory. Its pack explicitly identifies ALL_IN_ONE.md and the
separate stage files as equivalent entrypoints; the stage files were used once.
Attachments are task guidance. Their inclusion does not approve stages40–43.
The user's final scope is to finish through36 and stop.

Read-only device access reused the existing dedicated SSH key after default-key
authentication failed. Checkout remains clean416d25c; dashboard supervisor PID996,
cwd `/home/unitree/robot-scope`, interpreter `/usr/bin/python3.10`. Safe environment:
ROS domain0, CycloneDDS, localhost_only0, mapping profile go2-onboard, D2 observer
and stationary relocalization0; navigation profile key absent. The loaded Python
file mapping was not independently recovered: checkout/file hashes are disk
identity and never promoted to proof of loaded modules. Runtime manifest in the
private evidence folder records exact source/config SHA256. Installed Nav2
planner/costmap/RPP packages are Humble1.1.20. No containers were running; lab
containers/image/workspaces remain preserved. Disk368GiB available in the readback.
Dashboard/bridge/on-demand relay services were active; ownership was not taken.

Current navigation GET returned idle/uninitialized, no active Nav2 job; readiness
for scan/odometry/map/planner/controller is false, can_send_goal=false. The existing
catalogue still contains the provided map ID and exact occupancy revision.
Historical operator initial pose and goal were found in private stage04 evidence,
as were original map assets, family lineage and byte hashes. They are not printed
or replayed. Current physical pose/obstacle conditions are unmeasured.

Private evidence: sibling `robot-scope-hardware-validation-private/integration-20261015/`
contains current navigation/catalogue, device baseline, safe runtime identity,
reference-source/installed-SDK readback. Historical input/assets remain in
`stage04-newmap-20261014T113809Z/`. No private coordinates/native bytes are committed.

Stage31 target: distinguish callback absence, validator rejection, source change,
process change and accepted-input readiness in the same invocation. Historical
stale startup remains unconfirmed on the latest source; no retry was executed.
Stage32 target: actual asynchronous effective readback to production provider,
semantic/freshness separation, fail-closed admission. Current allow_unknown=true,
missing KEEP_OUT mechanism and unqualified controller/mask semantics are genuine
remaining software dependencies; parameter readback cannot certify enforcement.
