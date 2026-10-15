# 공유 통합 요청

기록 UTC: 2026-10-15T06:45:34.358571+00:00. 적용 source `22c7913c879afcca536a78d552dcdf98f0f53098` / base `7747ef7`. 계약은 pack04와 실제 MS `navigation_context()` projection이다. VERIFIED는 아래 명시한 software evidence 범위에 한정한다.

## MR-MS-001 — runtime/router/configure

**VERIFIED (software), native/live NOT_RUN.** MS가 담당을 수락하고 MR source 준비 뒤 단독 공유 창에서 app.py/runtime.py/API inventory/workflow wiring tests4개를 적용했다. 이후 이4개를 MR coherent source commit에 포함하도록 확인했다. 적용·검증 source `22c7913c879afcca536a78d552dcdf98f0f53098`.

app은 MR router를 한 번 등록하고 기존 navigation/mission/maps/spatial_routes와 configure_slam 뒤 `configure_mission_routes`를 호출한다. 별도 state root `navigation-runtime/mission-routes`, 기존 `MissionCoordinator`, 같은 `pipeline_coordination_lock`을 재사용한다. MR active/paused/canceling은 MS engine/map mutation을 차단하고 MS busy는 MR/legacy start를 차단한다. 편집·compile은 자원을 점유하지 않는다. legacy API는 유지하되 managed run의 admission 우회를 막는다.

actual MS manager/projection/configure + MR synthetic provider 교차8, 실제 app hook/API inventory tests, 전체 Python/JS/Chromium PASS. 이는 native runtime·물리 상호 배제 관측은 아니다. rollback은 해당 source의 MR hook과 연관 코드를 검토해 정상 revert하며 MS와 사용자 데이터는 보존한다.

## MR-MS-002 — native preview CLI 자원 창

**VERIFIED (software), 실제 native NOT_RUN.** MS가 `--mission-native-preview` store_true/default false와 configure 인자 연결을 수락·적용했다. 적용·검증 source `22c7913c879afcca536a78d552dcdf98f0f53098`. 기본 false는 `NATIVE_PLANNER_RESOURCE_WINDOW_REQUIRED`이며 실제 ROS/server 부재는 unavailable로 실패한다.

실제 adapter code에 synthetic transport를 주입한4검사와 CLI/wiring/전체 회귀 PASS. 고정 ComputePathToPose action, timeout·소유 요청 cancel cleanup, frame/nonfinite/rejection을 검사했다. lifecycle·SLAM/Nav2 기동·initialpose·ARM·motion goal 권한을 만들지 않는다. 장비/native 자원 창은 열지 않았다.

## MR-MS-003 — effective planner/footprint/runtime 정책 증거

**PROPOSED / 연결 BLOCKED.** 상대 수락·추가 공유 구현 근거 없음. production app은 `policy_provider`를 전달하지 않으며 기본 {}다. 따라서 작성/저장/compile은 가능하지만 start는 `RUNTIME_POLICY_NOT_ENFORCED`, `EFFECTIVE_PLANNER_CONFIG_UNAVAILABLE` 등으로 차단된다. 단순 하드웨어 확인 대기가 아닌 **소프트웨어 연결 의존성**이다.

필요한 read-only 계약: planner_config_digest, footprint_revision, 실제 robot_radius_m, runtime_policy_enforced와 유효성/출처. unknown/KEEP_OUT가 global/local costmap·controller·내부 재계획에도 유지됨을 증명해야 한다. wrapper의 한 번 path 검사·fixture true·작성용 0.25m 반경은 production proof가 아니다. navigation/gateway/Nav2 공유 파일을 고치려면 새 쓰기 소유권 창이 필요하다.

적용 SHA 없음. 실제 runtime/config 미확인. provider를 제거하면 fail-closed로 복귀해야 한다. 운영 설정/서비스 변경은 단계27 조건을 별도 충족한다.

## MR-MS-004 — 운영 pose source 정합성

**추가 공유 요청 PROPOSED.** MR consumer는 실제 localization_pose source와 odometry source를 분리하며 source 미상은 null이다. selected VSLAM 엔진을 Nav authority로 승격하지 않는다. MR source `22c7913c879afcca536a78d552dcdf98f0f53098`의 실제 MS projection 교차 fixture PASS와 process generation pin 회귀 PASS. pose sequence만 변하면 pin 유지, process/source generation 변경은 무효화한다.

추가 shared contract 수락/변경 완료를 추정하지 않는다. 실제 source generation/alignment와 장비 runtime 검증은 NOT_RUN이다. freshness는 readiness.localization을 읽고 can_send_goal과 분리한다.

## 후보와 자원 상태

MR source30개에 합의된 shared source/tests4개가 포함됐다. MS docs는 MS가 별도7747ef7로 게시했으며 MR이 수정하지 않았다. MS final CI success는 MR source 검증과 구분한다. MR exact b42b28f CI38694446361은 두 Linux 환경 success로 확인했다. PROGRESS/VALIDATION/CI.json에 기록했다. 장비 배포·서비스·센서 변경 없음.

## Integration follow-up — 2026-10-15, stages30–36

The new integration owner accepted shared software ownership from the user.
MR-MS-003 is now **PARTIAL: production observer/provider wired, enforcement still
BLOCKED by software**. Fixed asynchronous effective readback and canonical policy
meaning/freshness separation replace the default missing provider. The installed
profile still has no qualified global/local KEEP_OUT/unknown/controller/replanning
mechanism; config readback never asserts enforcement. No new run is authorized by
this change. See [runtime contract](../integration-acceptance/RUNTIME_POLICY_CONTRACT.md).
MR-MS-004 invocation token is propagated independently of pose sequence, including
same-PID restart and retired-envelope fences. Native preview now pins server GID,
ROS environment, own goal UUID and cleanup ownership; actual native remains NOT_RUN.
Latest source manifest/full candidate validation and remaining conditions are in
[the integration handoff](../integration-acceptance/HANDOFF.md). Historical published
software evidence above remains unchanged. No deployment or stage40–43 execution.
