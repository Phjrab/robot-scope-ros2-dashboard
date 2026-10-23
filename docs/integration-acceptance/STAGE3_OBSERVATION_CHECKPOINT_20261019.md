# Stage 3 sensor observation checkpoint — 2026-10-19

> 2026-10-20: 사용자 승인 후의 실제 배포·ARM 시험·정지 관측 결과와 한계는 [최신 실행 기록](STAGE3_ARM_RUNTIME_20261020.md)을 참조한다. 아래의 배포 전 상태와 제한은 해당 시점의 기록이다.

## Scope and state

This checkpoint implements historical global initialization followed by bounded
local sensor observations, with a separate sensor marker, direction axes and
short trail. It does not establish the robot body's position or actual location
accuracy. `body_pose` is null, `tracking_verified` is false and no operational TF,
navigation goal or motion command is applied. No deployment or service restart
was performed for this checkpoint. The last observed robot deployment was
`d7807de8f15fb457942039bb90ab41cf68d384c6`; this is a historical observation,
not a fresh availability check.

The received v0.3.1 backend remains byte-preserved and is not distributed here.
Its archive SHA-256 is
`0e4abbc70de139fdef45e90b6958d0f1f7c997a52b7ffb24bee718355bd12593`.
The source pin was generated on receipt, not supplied as an upstream manifest.

## Explicit observation policy

The initial 10 cm provisional policy was subsequently relaxed by the user for
observation development. 5 cm and 10 cm remain separately reported comparisons;
neither is a fixed selection gate in the reviewed compatibility adapter. The
original `RMSE_ABOVE_0.05M` diagnostic is retained. Fitting and scoring populations
are unchanged: no point subset is substituted to improve the reported result.

`ROBOT_SCOPE_OBSERVATION_ALLOW_AMBIGUOUS=1` is an additional explicit server
option, disabled by default. After the original backend finish, it may select
an otherwise eligible candidate rejected solely for `AMBIGUOUS_ALTERNATIVES`.
The rule is lowest original `rmse_m`, then original candidate index. All
alternatives, original gates and metrics are retained. The UI says
**모호한 미검증 추정** / `AMBIGUOUS SENSOR ESTIMATE · BODY UNVERIFIED`.
This rule does not prove that the selected physical location is correct.

Rigid transform, support, overlap, geometry, convergence/stationarity,
map/frame/source pin, epoch, receipt freshness and temporal continuity checks
remain. Global results remain historical until new scans confirm a sensor
observation in the same epoch. Source-clock and body-extrinsic verification
remain false. No timestamp is replaced with the current time to hide its age.

## Bounds and lifecycle

- Global processing remains separate from short local alignment.
- The global result cap remains 65,536 bytes. Compact shared comparison metadata
  avoids repeated policy text; candidates and diagnostics are not truncated.
- Local alignment keeps its 0.6-second end-to-end deadline and 1-second receipt
  freshness bound. Persistent workers avoid repeatedly loading the map.
- Three successive fresh scans are needed before `SENSOR_CANDIDATE`.
- Map/source/global-job replacement, reversed or stale time, epoch changes,
  cancellation, timeout and late replies invalidate the marker and trail.
  A new global search after loss requires an explicit request.
- `last_alignment` is historical diagnostic data, including after stop/loss.
  It is not a current pose. Temporary worker files and processes are cleaned.

## Evidence types and limits

**Synthetic/local tests:** full Python and JavaScript suites, strict boolean
override validation, 64 KiB near-limit results, cancellation and source/epoch
fences. A synthetic 16,000-point local scan against 25,666 map points aligned in
about 0.267 seconds on the desktop; this is not a robot performance guarantee.
Browser inspection confirmed the ambiguous label, sensor axes/marker and
removal of both sensor marker and body preview after an epoch mismatch.

For implementation commit `629a085`, the independent clean Git checkout ran
2,544 Python tests: 2,541 passed and 3 skipped (optional SVG plotting, optional
rosbags and the opt-in JavaScript geometry parity test). All 65 JavaScript test
files passed; Ruff, configured mypy checks and syntax checks for 99 frontend
modules passed. The original working tree additionally included preserved local
timing work: its 2,571-test result is not the published checkpoint's test count.
An earlier archive-only check failed four Git-dependent tests because the archive
had no `.git`; the clean Git checkout above resolved that verification setup issue.

**Stored real data:** three previously captured stationary scans, each with all
16,000 XYZ points, were replayed against all 25,666 stored map points. Off/on
runs used identical bytes, source pin and configuration. The explicit ambiguity
option selected original indices 10, 8 and 0 with RMSE 0.154952, 0.157924 and
0.254278 m; overlap was 1.0, 1.0 and 0.934375. All exceed both comparison
thresholds. Original ambiguity remains. These are three historical global
observations, not a real temporal tracking trial. The third scan's full-scan
RMSE is 0.378858 m; its original scorer's 0.75 m association rule is preserved.
Independent nearest-neighbor rescoring checked the complete input populations.

The older 7.04 cm result belongs to the earlier v0.3 saved-data experiment.
It is not evidence of v0.3.1 improvement or measured physical location error.

**Robot runtime:** isolated ARM64 Open3D compilation failed because its private
LAPACKE header include path was missing. A prepared retry script was not uploaded:
automatic approval review rejected that remote write twice, including once
after explicit user approval. No further remote retry is part of this checkpoint.
ARM64 Open3D import/tests, live dashboard tracking, actual body extrinsics,
absolute sensor-clock alignment and long-duration recovery remain unverified.

## Earlier CI failure

Main commit `3de44c7` had an Ubuntu 22.04 / Python 3.10 browser failure in
`subscription graph candidates require explicit opt-in and reanchor after mode
or source changes` (run `39197226103`). The fixture could reanchor after only
one stream changed, pairing old/new receipts. The branch change waits for a new
counterpart receipt and clears old pairing history while keeping each stream's
sequence high-water mark. It does not equate different topic subscription IDs.
The earlier focused browser rerun passed 9/9; publication CI must independently
verify the final branch commit.

## Publication boundary

Only selected reproduction data is included under
`docs/replay-fixtures/stage3-20261019`. Its manifest records hashes and provenance.
It contains PointCloud2.data payloads and their layout/header metadata, not
complete serialized CDR envelopes. Original backend source, credentials, SSH
keys, private course material, environment files, dependency builds and unrelated
session dumps are excluded. Existing uncommitted timing/recording work is
preserved locally and is not part of this checkpoint.
