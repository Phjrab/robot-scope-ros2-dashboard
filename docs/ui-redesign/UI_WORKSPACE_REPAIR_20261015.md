# Mapping, saved maps, camera capture and mission UI repair

Updated: 2026-10-15 21:13 KST. User requested inspection/fixes for these four
screens, reduced vertical space, and immediate publication/deployment when possible.

## Applied changes

- The dynamically inserted SLAM console spans the mapping grid. The live LiDAR
  map occupies the wide column again, alongside the existing mapping controls.
- VSLAM observation canvases appear for a selected or active visual engine.
  LiDAR selection no longer reserves empty visual-feature canvases.
- Native map details and preview appear after package selection. Native-only
  filtering also hides LiDAR conversion/crop tools; selecting another filter
  restores them. The selected native package receives its active highlight.
- Narrow capture panels stack camera-source choices and capture actions. Dual
  cameras stack when their containing panel is narrow, with bounded image height.
- Mission identity, editing mode, definition actions, validation, execution and
  history controls have separate rows. The layout responds to available panel
  width. The existing STOP link now opens Settings, where the global HUD lives.
- Reduced SLAM padding and paragraph spacing. At a 900px-high viewport, visual
  feature canvases shrink from 330px to 252px, native previews from 280px to
  240px, mission canvas from 495px to 342px. Main map height is bounded at
  360–560px; camera stages at 200–360px. Existing input/button sizes remain.

No API contracts, admission checks, mission persistence, map contents, camera
ownership, runtime policies or service configuration were changed by this UI commit.

## Source and validation

UI source: `a67c5f53da9d570d7679a6bf2a49e878599e0bea`, published on main.
It changes five static files plus `tests/e2e/ui_workspaces.spec.mjs`.

- Local JS: 381 PASS. Syntax: 83 modules PASS.
- Chromium: 36 relevant tests PASS after the final height adjustment, covering
  mapping/native selection, camera layout, mission authoring/history/actions,
  rejected actions, reconnect and responsive geometry.
- Four routes were rendered at 390, 768, 1024 and 1440px widths with synthetic
  data: no document horizontal overflow or browser page errors.
- Full local Python discovery: 1,998 tests, 2 skips, no failures. This run
  included the other chat's uncommitted policy tests; those files were excluded
  from the UI commit. Exact committed-source verification is the CI below.
- Exact UI CI [38732048177](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38732048177):
  Ubuntu 22.04/Python 3.10 and Ubuntu 24.04/Python 3.12 both PASS.

These are software UI regressions, not evidence of native localization, VSLAM
map reuse, policy enforcement or actual robot motion.

## Deployment and preservation

Initial transfer was blocked by loss of device connectivity; no UI mutation
occurred during that attempt. The user reported completing a reboot. Fresh
readback then showed clean checkout `1656e4d`, unchanged unit/environment files,
54 preserved map files, no active navigation/SLAM/mission/capture work, and zero
control command with no lease or deadman.

The device checkout was fast-forwarded to the exact UI source `a67c5f5`.
All 1,261 archive files matched. All five changed UI files returned HTTP 200,
the expected SHA256 and `Cache-Control: no-store`. Final checkout was clean.
No service restart, initialpose, goal, nonzero movement or camera action was issued.

The user's reboot started the following service invocations before deployment;
they were unchanged across the UI deployment:

| Service | Invocation ID |
| --- | --- |
| Dashboard | `bc9f62f591734339b657ad4df1ae613e` |
| Control bridge | `ac5bf5a37a5b470385c9268a042f6680` |
| Camera relay | `c99004f7d9194f0ab1a53a55d2a6110b` |

All 54 map hashes, selected-state hashes, mission API contents, unit definitions
and environment-file hashes matched across deployment. Aggregate configuration
fingerprint: `14f6b3e1abadca461db2e8bee2ff1618452dde4be9fabe549e59c2150999954e`.
No owned runtime/observer/FAST-LIO process remained. The later policy diagnostic
commit `a328879` is not included in this deployed checkout.

Private evidence is retained in the sibling hardware-validation directory under
`ui-workspaces-20261015`: pre/post-boot readbacks, deployment result, source file
manifest, regression logs, synthetic captures and final CI result. The device
release staging directory retains the original static-file backup.

UI work is complete. Refresh the dashboard to load the updated files. Any later
policy deployment or native acceptance remains a separate qualified operation.
