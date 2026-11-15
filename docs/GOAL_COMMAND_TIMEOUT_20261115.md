# Goal canceled after forward motion

The supervised goal on 2026-11-15 at 18:24 KST advanced, then was canceled with
`navigation control lease was lost`. The manager's preserved first lease-end
reason was `command_timeout`. The operator confirmed actual forward motion.
No additional goal was sent during diagnosis.

The last fresh map pose had 0.589934868 m XY error to the requested goal,
0.618 m remaining path feedback, and 6.35 s navigation time. Its measured
speed was still 0.20997 m/s. Thus 59 cm is the last fresh pre-stop goal error,
not a measured final stopped position. The action did not report success.

At each replan, the controller logged future extrapolation of roughly 7–9 ms
followed by a missed 10 Hz control cycle. The pinned Nav2 1.1.20 Shim's initial
heading branch restamped a path point to wall-clock now, then performed a
blocking TF lookup. The existing final-heading overlay did not cover this
branch. Its fallback still called the primary controller after the wait.
The 200 ms command watchdog correctly revoked the lease when commands expired.
The incident does not contain a complete timestamped command stream, so the
exact duration of the initiating gap is not claimed.

The overlay now uses the existing bounded common-time reconstruction for the
robot and sampled path point. It computes heading in that robot's frame without
waiting for future TF or modifying source messages. Short paths still hand off
to the primary controller; missing/stale TF and rotation collisions do not
silently fall through. Watchdogs, speed limits, TF freshness, localization
quality and goal tolerances are unchanged.

The independent `MAP ERROR` UI fault was a retained catalog mismatch message:
the exact cached-map reuse branch never cleared the earlier error after catalog
recovery. It now clears that old error before redrawing; real revision mismatch
and a new rendering error remain visible. Regression tests execute the actual
map-selection function through mismatch, recovery and persistent-error cases.

Native tests use an isolated localhost ROS domain, real Shim/TF/checkers and a
spy primary controller, with no robot command publishers or navigation goals.
They cover replans with 7, 40 and 60 ms TF delay, required initial turns, short
paths and rejection of stale inputs. Actual arrival after deployment requires
a separately supervised fresh goal and is not inferred from these tests.

The exact previously deployed overlay was loaded into the same native replan
test and failed its 50 ms latency assertion: 101.986, 101.761 and 101.543 ms for
the three delays. The candidate library took 0.099, 0.013 and 0.011 ms. The test
records the actual loaded shared-library path. All five final native variants
passed. An earlier fixed-variant cleanup timeout passed on targeted rerun;
the final rebuilt suite passed all variants together. JavaScript: 779 passed.
