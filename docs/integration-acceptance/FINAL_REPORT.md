# Integration final report — through40

Stages30–36 software integration and the authorized stage40 deployment/localization window are finished. Candidate863682e was deployed; existing initialpose1 and180s stationary observation completed, with goal/motion0 and owned cleanup confirmed. Full live acceptance and SOFTWARE_CLOSURE remain false. Actual policy evidence was unavailable; full TF authority and independent map alignment remain unproved. See [STAGE40_VALIDATION.json](STAGE40_VALIDATION.json), [DEPLOYMENT_ACCEPTANCE.md](DEPLOYMENT_ACCEPTANCE.md) and [LOCALIZATION_LIVE_ACCEPTANCE.md](LOCALIZATION_LIVE_ACCEPTANCE.md).

The user additionally requested the current dashboard UI changes, explicitly choosing the global control-status HUD and its SOFTWARE STOP only in Settings (the existing Controls-page STOP remains). UI381 JS/96 Chromium/83-module syntax checks passed; commit1656e4d was applied without restart and all3 HTTP static hashes matched. See [UI_ACCEPTANCE.md](UI_ACCEPTANCE.md). This does not reopen localization or41–43.

Smallest next software work: preserve raw bounded policy observer failure reasons on incomplete parameters, isolate effective parameter/lifecycle readback, then implement qualified policy ingestion/enforcement. NativePlanner product execution, MS native map reuse and complete retained-map export still require their own qualified native conditions. Historical stale startup cause remains unconfirmed. No follow-up is scheduled.

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