# Integration final report — through40

Final user instruction: stop and finish here. Scope was briefly extended to41,
but no41 operation began before the stop request. No additional device action
or background continuation is pending.

Candidate `47c77af19246bd6a455ee873a7c55884ed6e4122` is now deployed, including
the a67c5f5 UI repairs and bounded policy diagnostics. The approved one-start,
no-initialpose policy window completed60 seconds and owned cleanup. All60 policy
samples were unavailable (59 readback-timeout reasons); independent graph samples
showed five unique authorities and ten ready services, without proving replies.
No deadline/freshness was relaxed. Exact source/runtime/config, tooling corrections,
preservation, regressions and limits are in [POLICY_RUNTIME_WINDOW.md](POLICY_RUNTIME_WINDOW.md)
and [POLICY_RUNTIME_WINDOW.json](POLICY_RUNTIME_WINDOW.json).

Final inspection at2026-10-15T13:03:52Z: clean main47c77af, dashboard PID54752,
HTTP200,1265 matching source files,54 maps and five selected-state files preserved.
Bridge/camera invocations remain unchanged. Navigation/session/goal idle,
initialpose0, lease/deadman false, command0 and no owned runtime/observer remain.
The five updated UI files are served with exact hashes and no-store. Global
HUD/STOP stays Settings-only by user choice; the Controls-page STOP remains.

This60-second diagnostic does not replace the prior localized180-second result.
Full live acceptance and SOFTWARE_CLOSURE remain false; NativePlanner product
execution, MS native reuse and MAP-02 completeness remain unverified. No41–43
operation or additional runtime window was performed. Next minimum policy work:
bounded per-endpoint future state and tick/batch timings, preserving500ms/750ms
and semantic revisions. Historical stale-startup cause remains UNCONFIRMED.
No background continuation is scheduled.

## Historical stage36 software snapshot

Available software follow-up through36 is finished and handed off. Full
SOFTWARE_CLOSURE=false: MR-MS-003 enforcement still needs software work, while
historical startup/native/MS reuse/MAP-02 require additional qualified evidence.
The user's stop-after36 instruction is preserved. No deployment or motion occurred.

Changed units: bounded localization input diagnostics and alignment/source/process
fences; real async runtime parameter/lifecycle readback with fail-closed provider;
stable semantic pins; native planner executor/environment/server/UUID/path and
late-cancel ownership; native wait outside the shared lock with a retained reservation; conservative
KEEP_OUT footprint overlap; frozen native completeness attestation and honest
unknown/subset coverage. Existing UI/mission/adapter structure is retained.

Local full validation passed:1987 Python tests (1985pass,2skip,0fail),381 JS,
96 Chromium E2E. Static/syntax/dependency checks pass. Coverage75%; mypy covers its
four configured modules. Exact source, commands, skips, log SHA256 and publication
CI are in [VALIDATION.json](VALIDATION.json). Native ROS/camera/live acceptance is
NOT_RUN and cannot be inferred from these fixture results.

Device readback is the older clean disk checkout416d25c; no loaded release proof
or new runtime is claimed. Original maps, initial-coordinate evidence, history,
receipts, bags and VSLAM installs were preserved. No service/camera takeover,
pipeline start, initialpose, goal or movement was attempted. Nothing continues
in the background. [HANDOFF.md](HANDOFF.md) gives remaining conditions and the next
minimum software/native units; [ACCEPTANCE_MATRIX.json](ACCEPTANCE_MATRIX.json)
keeps each blocked row separate.

Published source candidate: `4b189d1f59fb08667faaf3922f08b6e145f0db4b`. Exact source CI run: [38716730829](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38716730829); result: SUCCESS on Ubuntu22.04/Python3.10 and Ubuntu24.04/Python3.12, recorded in VALIDATION.json and CI.json. Subsequent documentation tip CI is a separate run and is never inferred from this source run.

Source CI per Linux job:1987 Python tests (1986pass,1 optional-rosbags skip,0fail),381 JS and96 Chromium E2E PASS. Linux /proc coverage runs there; no native ROS/camera/motion acceptance is included.
