# REPLAY run review

Read-only archived evidence. Missing events are UNOBSERVED.

Result: canceled
Timing: RESULT_RECEIPT_NOT_SUCCESS

```json
{
  "schema": "robot-scope.run-review-summary.v1",
  "mode": "REPLAY",
  "provenance": {
    "code_sha": "5c1ffe3ba3c070e67e143d39b65650cc8dba5f2e",
    "parameters_revision": "71933badef736b1361f1162355527488a9350b86a8b4b8865b81c38031100387",
    "parameters_digest": "48f10a36346f529cbd063fc848f4e2efaf727b6318ec982072524cea57dccbc8",
    "map_id": "9a382e3eb990fb02fe1a3569",
    "map_revision": "d5733a293effbd9567cdb9165472e15c2be8ab0adef7cf05f99ec39f19578552",
    "goal_id": "b86cc8afa7c04477cfed0847adafdca5",
    "data_kind": "REAL",
    "source_id": "sha256:f34e33b3955fff231dbc824075e45683591b7766c8ad7a55ae317e5014a70bb9"
  },
  "input_digest": "ebbcd4fee9a375680f3153a0d18a7e53b4d9e2a6e46b639ab13d5547519d360a",
  "requested": {
    "x": 1.269368163770345,
    "y": 1.3412287309052333,
    "yaw": -0.5031337053957546
  },
  "result_state": "canceled",
  "result_received_ros_ns": "1793259454360504268",
  "result_timing": "RESULT_RECEIPT_NOT_SUCCESS",
  "near_result": {
    "pose": {
      "x": 0.7097408542129586,
      "y": 0.44324320296931546,
      "z": 0.1025830860043633,
      "yaw": 1.285109909887064
    },
    "stamp_ns": "1793259454398248672",
    "received_ros_ns": "1793259454464592583",
    "error": {
      "xy_m": 1.0580929703881354,
      "yaw_rad": 1.7882436152828185
    }
  },
  "after_stop": {
    "pose": {
      "x": 0.7292610357078283,
      "y": 0.43402360025234255,
      "z": 0.059419633198612924,
      "yaw": 1.3592798408652824
    },
    "stamp_ns": "1793259458798790693",
    "received_ros_ns": "1793259458853342862",
    "error": {
      "xy_m": 1.0558109958069524,
      "yaw_rad": 1.862413546261037
    }
  },
  "native_report_final": null,
  "motion_vs_correction": {
    "body_odom_translation_m": 0.013000389586251753,
    "body_odom_rotation_rad": 0.08176507574871998,
    "map_odom_translation_m": 0.051874424315771356,
    "map_odom_rotation_rad": 0.012235587348576018
  },
  "translation_semantics": "3D_TRANSLATION_NORM_NOT_XY",
  "observations": {
    "dispatch": 1,
    "accepted": 1,
    "rejected": "UNOBSERVED",
    "initialization": "UNOBSERVED",
    "path_update": 4,
    "obstacle_appeared": "UNOBSERVED",
    "stale": 1,
    "reconnect": 1,
    "recovery": "UNOBSERVED",
    "cancel": "UNOBSERVED",
    "result": 1,
    "command_zero": 3,
    "bridge_ack": "UNOBSERVED",
    "measured_stop": 1,
    "contact": "UNOBSERVED",
    "map_change": "UNOBSERVED",
    "pose": 35,
    "scene": "UNOBSERVED",
    "input_gap": "UNOBSERVED",
    "unclassified": "UNOBSERVED"
  },
  "quality": {
    "events_without_independent_time": 9,
    "observation_gap_count": 0,
    "cross_host_latency": "UNOBSERVED"
  },
  "event_table_truncated": false
}
```

| # | Event | Replay ns | Original time |
|---:|---|---:|---|
| 0 | pose | 0 | None |
| 1 | dispatch | 1000000 | 1793259451065676513 |
| 2 | stale | 2000000 | None |
| 3 | accepted | 3000000 | None |
| 4 | path_update | 4000000 | 1793259451068033802 |
| 5 | reconnect | 5000000 | None |
| 6 | pose | 433714876 | 1793259451498391389 |
| 7 | pose | 933863650 | 1793259451998540163 |
| 8 | path_update | 934863650 | 1793259452098080320 |
| 9 | pose | 1434596787 | 1793259452499273300 |
| 10 | pose | 1933722744 | 1793259452998399257 |
| 11 | path_update | 1934722744 | 1793259453128070548 |
| 12 | pose | 2433691273 | 1793259453498367786 |
| 13 | pose | 2934254418 | 1793259453998930931 |
| 14 | command_zero | 2935254418 | None |
| 15 | path_update | 2936254418 | 1793259454157980039 |
| 16 | result | 3295827755 | 1793259454360504268 |
| 17 | command_zero | 3298836328 | 1793259454363512841 |
| 18 | command_zero | 3298836329 | 1793259454363512841 |
| 19 | pose | 3733322153 | 1793259454797998666 |
| 20 | pose | 4234003077 | 1793259455298679590 |
| 21 | pose | 4833095322 | 1793259455897771835 |
| 22 | pose | 5233440170 | 1793259456298116683 |
| 23 | pose | 5734014282 | 1793259456798690795 |
| 24 | pose | 6234168062 | 1793259457298844575 |
| 25 | pose | 6834050188 | 1793259457898726701 |
| 26 | pose | 7333899746 | 1793259458398576259 |
| 27 | measured_stop | 7734114180 | 1793259458798790693 |
| 28 | pose | 8134089003 | 1793259459198765516 |
| 29 | pose | 8733112106 | 1793259459797788619 |
| 30 | pose | 9233623991 | 1793259460298300504 |
| 31 | pose | 9733815680 | 1793259460798492193 |
| 32 | pose | 10334228525 | 1793259461398905038 |
| 33 | pose | 10734060059 | 1793259461798736572 |
| 34 | pose | 11334606419 | 1793259462399282932 |
| 35 | pose | 11833948622 | 1793259462898625135 |
| 36 | pose | 12334485541 | 1793259463399162054 |
| 37 | pose | 12934144983 | 1793259463998821496 |
| 38 | pose | 13433906088 | 1793259464498582601 |
| 39 | pose | 13934366713 | 1793259464999043226 |
| 40 | pose | 14433660517 | 1793259465498337030 |
| 41 | pose | 14934180746 | 1793259465998857259 |
| 42 | pose | 15534199724 | 1793259466598876237 |
| 43 | pose | 16033953200 | 1793259467098629713 |
| 44 | pose | 16533509979 | 1793259467598186492 |
| 45 | pose | 17133865843 | 1793259468198542356 |
| 46 | pose | 17634041081 | 1793259468698717594 |
| 47 | pose | 18133944521 | 1793259469198621034 |
