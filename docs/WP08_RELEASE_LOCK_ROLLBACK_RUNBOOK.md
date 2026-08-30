# WP08 Competition release lock, rollback, and field runbook

## Scope and safety boundary

This runbook freezes a previously verified software/configuration identity and
packages it for offline transfer. It does not grant motion authority, start a
service, clear an E-stop, activate a model, rebuild an engine, install a
package, or change a network target. Competition Lock is a configuration
freeze only; it is not a physical stop and never replaces the physical remote
or field E-stop.

The release command has only `validate-manifest`, `build`, and `verify`.
There is deliberately no `update`, `pull`, `install`, `activate`, `restart`, or
"update all" command. Building requires a clean tracked checkout at the exact
40-character commit, a persistent locked Competition state, a target-validated
active model registry, and a target-generated Python install manifest. Output
is created only under `runtime/releases/` with private permissions.

## Release identity and private inputs

Copy `deploy/competition-release-manifest.json.example` to a private file
outside Git, replace every example identity, and validate it. Do not put a
bridge key, password, token, complete environment, MAC address, private IP,
absolute host path, Dataset name, or venue-private detail in the manifest.
The network field is only the SHA-256 of a reviewed, redacted configuration
summary. Acceptance report IDs must identify reports whose recorded commit is
the same `git_commit`.

On each target, generate `runtime/release-input/python-install-manifest.txt`
from the already validated environment (for example, an approved
`python -m pip freeze --all` record). This file is release evidence, not an
installer. Keep system/ROS package and external workspace revisions in the
acceptance evidence. Never copy credentials or a complete environment file
into `runtime/release-input`.

Copy the private JSON acceptance reports named by the manifest to
`runtime/release-input/acceptance/<report-id>.json`. Packaging rejects a report
from another commit, any reported FAIL/BLOCKED, and any observed supervised
scenario that lacks a present-operator PASS. NOT_RUN hardware rows remain a
release blocker even when a hardware-free candidate review is otherwise green.

~~~bash
python3 scripts/robot_scope_release.py validate-manifest /private/release-manifest.json
python3 scripts/robot_scope_release.py build /private/release-manifest.json
python3 scripts/robot_scope_release.py verify runtime/releases/<release-id>.zip
~~~

The bundle contains a Git archive of the exact commit, Python installation
record and requirements, Node lock, active/previous model packages and target
engines, service examples, doctor/acceptance tools, this runbook, and hashes
for every payload. The verifier rejects traversal, links, runtime directories,
Dataset/map captures, private env files, secret-like content, missing models,
or checksum changes. The source archive and model registry are read-only.

## Competition Lock mutation inventory

| Change | Locked behavior |
|---|---|
| Git pull/source update | No dashboard or release-tool endpoint exists; field procedure forbids it. |
| Python/Node/system package install | No endpoint or release-tool action exists; perform only outside a locked release window. |
| Model activation/rollback | Local model tool calls the persistent Competition gate and fails closed if state is missing or locked. |
| Engine rebuild | No dashboard endpoint exists; release builder accepts only target-validated registry artifacts. |
| Robot network target | Existing server mutation calls `require_unlocked`; release manifest stores only a fingerprint. |
| Camera profile | No dashboard profile editor exists; environment/service edits are forbidden while locked. |
| PointCloud RAW/limit | Existing settings mutation calls `require_unlocked`; RAW stays supervised diagnostic-only. |
| Service topology | No generic topology editor exists; service examples are inert files and lifecycle controls cannot edit units. |
| AUTO speed/timeout | ASSISTED/AUTO remain disabled pending hardware/rule acceptance; no release-tool mutation exists. |

Safety cleanup remains available: STOP, DISARM, lease release, Dataset finalize,
and orderly shutdown must not be blocked by a configuration freeze.

## Startup checklist

Stop at the first failed condition. Record PASS/FAIL/BLOCKED and evidence for
every line; never skip a failed dependency by changing the release in place.

1. Power BE5100M. PASS: expected LEDs and management network only. Stop: unknown cabling, smell, heat, or unstable power.
2. Connect the external Orin wired link. PASS: expected interface and redacted config fingerprint match. Stop: target/NIC mismatch.
3. Power Go2 and internal Jetson Wi-Fi. PASS: reserved identities and routed topology match without ad-hoc DHCP changes. Stop: duplicate or unexpected host.
4. Check robot-side camera/perception. PASS: services report expected version and no stale result is ready. Stop: version/hash mismatch or duplicate producer.
5. Start external Robot Scope by the approved manual service procedure. PASS: health reports the release commit. Stop: service/unit differs from release.
6. Connect the browser. PASS: one cockpit session loads without changing ARM/mode. Stop: stale UI or reconnect restores authority.
7. Check LowState/control bridge. PASS: fresh LowState, signed bridge readiness, DISARMED, deadman released, zero command, no lease. Stop: publisher cardinality, key identity, or zero-state mismatch.
8. Check RealSense source/transport/decode. PASS: expected profile, fresh complete frames, one producer, bounded viewers. Stop: profile, age, decode, or duplicate mismatch.
9. Check model identity. PASS: active/previous IDs, package hashes, engine hashes, JetPack and TensorRT match the manifest. Stop: any mismatch.
10. Select policy. PASS: SHADOW only unless separately accepted ASSISTED/AUTO evidence exists. Stop: unintended authority or disabled mode appears enabled.
11. Check storage. PASS: Dataset/map/log volumes exceed their configured reserve. Stop: low/unknown space or wrong mount.
12. Confirm physical stop. PASS: operator identifies and can reach the physical stop/remote. Stop: unavailable or untested control.
13. Run the separately approved low-speed supervised smoke. PASS: deadman-held bounded motion and immediate release stop, then DISARM. Stop: any unexpected motion, latency, stale state, or fault.

With robot power off, steps 3–4 and 7–13 are `NOT_RUN` or `BLOCKED`, never
inferred PASS from unit tests.

## Shutdown and run preservation

1. Confirm the robot is stationary; if uncertain, use the physical stop path.
2. Abort or complete the exact Mission and verify terminal state.
3. DISARM, release the exact lease, release deadman, and verify zero command.
4. Use Dataset `STOP & FINALIZE`; verify `COMPLETED`, manifest and sample count. Closing the browser is not finalize or robot stop.
5. Save bounded diagnostics and the matching acceptance report.
6. Complete `deploy/competition-run-record.json.example` with run, release, commit and model IDs.
7. Back up Dataset/logs to a new restricted snapshot; redact IPs, paths, credentials and venue details before sharing.
8. Stop services in the approved dependency order without changing enable policy or unit topology.
9. Power off only after writes are durable and operators confirm shutdown.

## Rollback

Rollback is an explicit stationary, DISARMED, no-lease operation. Preserve
`runtime/`, maps, Dataset, model registry, private logs and host environment.
Do not use `reset --hard`, force pull, recursive deletion, or an installer that
changes service enable/start policy.

### Dashboard

1. Record the failed release and current service state; finalize Dataset.
2. Verify the focused previous commit or offline archive and its checksums.
3. Switch only the source/venv reference according to the approved host procedure; do not overwrite runtime data.
4. Run doctor and read-only acceptance for that release.
5. Restart only the explicitly approved service if it was previously active; verify version, DISARMED/zero/no-lease state.

### Robot-side agent

1. Preserve current package/venv/service and config fingerprint as a rollback record.
2. Select the previously verified agent package/venv without editing the live config.
3. Verify network, camera profile, JetPack/TensorRT and service unit identity.
4. Explicitly restart only the agent service through the field procedure.
5. Run shadow smoke; do not ARM or enable AUTO.

### Model

1. Keep Competition Lock enabled during diagnosis. Unlock only after stationary, DISARMED and all existing blockers pass.
2. Use the local model tool with exact active-model confirmation for the atomic active/previous swap.
3. Revalidate package, schema, engine, JetPack/TensorRT and build-log hashes.
4. Re-lock, run shadow smoke, and confirm rollback did not create a lease, ARM, ASSISTED or AUTO state.

## Final acceptance and release decision

Required evidence is: CI green; read-only acceptance with no unexplained
FAIL/BLOCKED; every required supervised scenario; verified offline boot with
internet removed; laptop-browser disconnect; model rollback; cold boot; soak;
storage reserve; and a complete field-checklist dry run. Each report must name
the same release commit. Hardware-free tests prove schema, hash, archive and
lock behavior only.

The current WP08 code change alone is **not competition-deployable**. It becomes
deployable only after a real package is built from both Jetsons, the above
hardware/offline checks pass, and field/operator approvals are recorded. A
failure or missing item remains FAIL/BLOCKED; do not edit evidence to green it.
