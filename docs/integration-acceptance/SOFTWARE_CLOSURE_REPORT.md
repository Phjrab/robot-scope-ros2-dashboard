# Stage36 software closure assessment

> Current scope through40: the user explicitly extended the completed stage36 snapshot. Candidate863682e was deployed; initialpose1 and180s stationary observation were completed and owned resources cleaned. Live acceptance remains partial/false. See [STAGE40_VALIDATION.json](STAGE40_VALIDATION.json), [DEPLOYMENT_ACCEPTANCE.md](DEPLOYMENT_ACCEPTANCE.md) and [LOCALIZATION_LIVE_ACCEPTANCE.md](LOCALIZATION_LIVE_ACCEPTANCE.md). Earlier stop-after36/no-deployment statements below describe the historical software snapshot.41–43 remain NOT_RUN.

**PARTIAL — available stages30–36 work completed; SOFTWARE_CLOSURE=false.**
This is a source/publication candidate, with no deployment or motion acceptance.
The user instructed this chat to stop after36. [VALIDATION.json](VALIDATION.json)
records exact source identity, local commands, log hashes, skips and exact CI;
[SOURCE_MANIFEST.json](SOURCE_MANIFEST.json) pins the tested source bytes.

The candidate fixes reproducible alignment revival, duplicate source progress,
retired invocation receipt renewal and native planner cancellation/ownership
races. It adds bounded startup evidence, a real asynchronous runtime readback
and default production policy provider, semantic context pins, conservative
KEEP_OUT footprint-edge checking, and honest full-map completeness evidence.
All existing UI, adapters, mission coordinators, data bounds and motion gates
are reused. No freshness/startup deadline is enlarged or source stamp rebased.

Required unfinished software is MR-MS-003 enforcement: versioned native collision
profile, immutable map/annotation mask producer, global/local/controller and BT
replanning ingestion, restart/clear retention and qualified map-epoch witness.
Current installed legacy profile permits unknown and has no qualified KEEP_OUT
mechanism. The new provider reports false for all enforcement scopes and blocks
admission. Readback/config/lifecycle alone cannot make these true. Raw-observation
production tests establish the negative contract, not positive enforcement.

Historical stale startup remains UNCONFIRMED; code counterexamples were fixed
without promoting them to the historical root cause. Product NativePlanner,
MS camera/native lifecycle, native map reuse/alignment and MAP-02 full retained
map remain NOT_RUN/BLOCKED. The installed SDK header lacks a documented full
iterator/total/revision guarantee; a supported qualified exporter is still needed.

Local verification: Python1987,1985pass/2skip/0fail; JS381pass; Chromium96pass;
coverage75%; ruff/frontend syntax/dependency audits pass. mypy's configured four
modules do not establish whole-app type correctness. macOS skips optional rosbags
and Linux /proc behavior; Linux CI is reported separately. No native ROS, actual
camera, stationary or motion acceptance was run by these suites.

There are no deployed files, service/profile changes, migrations or data cleanup.
The private maps, mission/run/receipt history, bags and VSLAM installations remain
in place. Public JSON preserves null loaded runtime/config provenance and safe
unavailable live_plan/ETA. Runtime disk checkout is not a loaded release attestation.

Future stage40 needs a separately current deployment/resource window, exact
candidate/config/helper/library manifest, camera ownership/shared inode proof,
current operator and physical stop/recovery conditions, and layer-specific
rollback. Source rollback is a normal revert without rewriting main; data reader
compatibility is checked on copies; device rollback belongs to that future window.
No background job, polling, automation or later hardware step continues after36.

Published source candidate: `4b189d1f59fb08667faaf3922f08b6e145f0db4b`. Exact source CI run: [38716730829](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38716730829); result: SUCCESS on Ubuntu22.04/Python3.10 and Ubuntu24.04/Python3.12, recorded in VALIDATION.json and CI.json. Subsequent documentation tip CI is a separate run and is never inferred from this source run.

Source CI per Linux job:1987 Python tests (1986pass,1 optional-rosbags skip,0fail),381 JS and96 Chromium E2E PASS. Linux /proc coverage runs there; no native ROS/camera/motion acceptance is included.
