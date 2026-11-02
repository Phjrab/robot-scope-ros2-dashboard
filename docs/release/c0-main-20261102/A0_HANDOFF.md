# A0 인계 — C0와 I0를 포함한 main에서 현장 검증 재개

이 문서가 통합 후의 최신 인계 기준이다. **C0와 I0 소스는 main에 인수됐으며 A0가 다시 병합할 필요가 없다.** 기존 I0 인계의 “C0 미인수·미수리”와 역할 분담은 당시 기록이다. 최신 C0 구현의 실장비·현장 검증은 A0가 통합 main에서 이어간다. 이 인계는 과거 시험창이나 이동 승인을 갱신하지 않는다.

## 소스·검증 기준

| 항목 | 고정 기준 |
|---|---|
| 병합 전 main | `31ebb43ef7196bba7eced45ed37854eabc5e2927` |
| 인수 C0 | `cc7e0fc526eb2fec365f1df84d1dd5f422da83d1` |
| 이미 main에 포함된 I0 | `ae41a9b6cf5cf5c7c133e818e3fad4693eb2053e` |
| C0 원본 브랜치 | `review/20261030-c0-3d-field-sweep` — 원격 유지 |
| 병합 전 main 복구 태그 | `archive/20261102/pre-c0-main-31ebb43ef719` |
| C0 원본 복구 태그 | `archive/20261102/c0-merge-source-cc7e0fc526eb` |

통합 검증 대상과 실제 검사 결과는 [SOURCE_LOCK](SOURCE_LOCK.json), [MERGE_REPORT](MERGE_REPORT.md)를 따른다. 최종 main SHA와 그 SHA의 표준 CI·I0 통합 CI는 게시 후 최종 전달 receipt로 확정한다. 이전 main 또는 C0 단독 CI 성공을 통합본 성공으로 대신하지 않는다.

검증 기준 후보 `aaf5216a16e3cfb164dc04db8f7f5ca3128ccd0c`는 표준 CI3개 작업과 I0 통합 CI 모두 SUCCESS다. C0 ASGI37/전체 앱8, I0 제품9/콘11, Linux 두 환경의 전체 browser333/mission10을 확인했다. 이 문서를 확정하는 후속 commit은 제품 코드를 바꾸지 않는다. A0는 최종 전달 receipt의 main SHA와 현재 실행 장비 SHA를 별도로 대조한다.

**DEVICE_NOT_RUN**: 이 소스 통합에서는 로봇/Jetson 접속, 배포, 서비스 재시작, 센서 실행, 실제 ROS graph·INITIAL POSE·goal·TF·속도/자세 명령과 주행을 수행하지 않았다.

## 그대로 인수한 동작과 조건

C0의 3D/2D 지도 조합·ID/revision/계보, 불변 PCD 사본의 복사형 2D 변환, 사용자 선택·교정 보존, 미전송 X/Y/yaw 초안→센서 제안→높이·roll·pitch 명시 확인→정확한 관측 종료→handoff→Nav2→명시 INITIAL POSE→별도 정합 요청 흐름을 사용한다.

- 사용자 불확실 반경·각도를 다시 필수 입력으로 요구하지 않는다. 새 UI의 원본 초안에는 임의 bounds를 채우지 않는다. `bounds_source=server_policy`, `effective_bounds={xy_m:0.25,yaw_rad:0.20}`는 서버 검증 한도이며 실측 불확실성·정확도가 아니다. 기존 명시 bounds API 호환성과 별도 handoff 한도도 유지한다.
- 조건부 proof, 후보 그룹과 모든 구성원 검증, source/session/generation·지도/교정·capture-time pose·신선도/TTL·품질·모호성 조건을 유지한다. 서로 다른 적격 가설을 합치거나 최저 잔차 후보를 자동 선택하지 않는다. 미확인 z/roll/pitch를 0이나 과거값으로 채우지 않는다.
- 관측 종료는 정확한 세션의 stop dispatch 수락·비활성·작업 종료와 matching release acknowledgement로 확인한다. 종료 수락이나 inhibition 해제가 불명하면 hold를 유지한다. timeout·bridge 재시작·임의 상태 변경을 해제 증거로 사용하지 않는다. 서명·STOP/lease·소유권 조건은 계속 적용한다.
- 화면 열기·초안 복원·새로고침·Nav2 시작이 INITIAL POSE, 정합 또는 goal을 자동 전송하지 않아야 한다. INITIAL POSE의 고정 점·방향, 실제 추정 로봇 URDF, 목표 URDF를 구분한다. 미확인 health는 null/`—`, 실제 측정 0과 gateway의 실제 집계는 0으로 구분한다.
- `MATCH_ARMED`는 정합 요청 수락 상태이며 수렴·지속 위치추정·주행 준비 완료가 아니다. 합성 준비 API의 MATCH_ARMED와 별도 진단 read의 `OUTCOME_UNKNOWN / HANDOFF_MATCH_CURRENT_UNCONFIRMED`도 합쳐 성공으로 쓰지 않는다.

I0의 `/extensions`, 지도 job·전체 사본 저장·재조회, C1/C3 관측/renderer, C5 scoped helper, C6 재생, C7 CLI와 콘 표시를 함께 인수했다. `ROBOT_SCOPE_EXPANSION_MULTIMAP`, `SCENE`, `REPLAY`, `USABILITY`, `RUNTIME`은 모두 기본 OFF다. 운영 owner가 없으면 `BLOCKED_AUTH`, native는 `BLOCKED_NATIVE_IDENTITY`, 보호는 `ADVISORY_ONLY`다. 화면이나 flag만으로 권한·worker·제어를 시작하지 않는다. CONES도 기본 OFF이며 기존 구독을 공유한다. 합성 콘은 `SIMULATED / FLAT_DEMO_ONLY / HEIGHT_UNVERIFIED`를 유지한다. [I0 flag와 복구](../../integration/i0/FEATURE_FLAGS_AND_ROLLBACK.md), [콘 인계](../../integration/i0/teammate-obstacle/HANDOFF.md)를 참고한다.

## A0의 실장비·현장 검증 순서

아래는 모두 이번 통합에서 **NOT_RUN**이다. 이미 구현한 기능을 다시 개발하는 목록이 아니라 현재 장비에서 검증할 목록이다. [최신 C0 체크리스트](../../c0-field-validation/C0_REMAINING_WORK.md)의 장비 담당 “C0”는 과거 분담이며 이후 담당은 A0다.

| 순서 | 확인할 일 | 완료 근거와 다음 조건 |
|---|---|---|
| 1 | 현재 장비 readback, 후보 배포·복구 준비 | dashboard와 bridge 각각의 실제 loaded source·프로세스/서비스 소유권·관측/제어 점유·정지 상태를 확인한다. `map1`/`map1_2D` ID/revision/계보·교정·선택, P1/P2 지도 결합과 보호 파일 해시를 보존한다. 현재 base에 맞는 패키지·백업·복구를 준비하고 적용 후 실제 두 프로세스 및 HTTP 자산을 대조한다. |
| 2 | 현재 초안과 정지 센서 관측→제안→명시 확인·적용 | 현재 지도 위 X/Y/yaw와 정지 가정을 확인한다. 실제 bridge 명령 억제·서명·소유권, 스캔과 같은 시각 자세의 source/session/generation·프레임·교정·신선도를 검증한다. 센서 수신, 제안의 품질/모호성, 높이·roll·pitch 명시 적용과 서버 readback을 각각 기록한다. |
| 3 | exact stop→handoff→Nav2→INITIAL POSE→별도 정합 | 정확한 관측 종료·작업 정리·차단 해제 및 제어권 복구를 확인한다. 각 단계의 수락/거절을 현재 지도·세대에 결속하고 실제 Nav2 노드/센서/TF를 확인한다. 초안은 명시 재확인 후 전송하며 자동 재전송·goal 0을 확인한다. |
| 4 | 지속 보정·Nav2 TF/odom·화면 연속성 | FAST-LIO 상대 추정과 현재 스캔 기반 저장 지도 보정, 기존 단일 TF 경로·Nav2 입력, 갱신/중단/세대 변경 무효화를 실제 연속 구간으로 확인한다. 잔차·겹침을 위치 정확도라 부르지 않는다. 현재 추정/목표 URDF와 오래된 값 표시를 확인한다. |
| 5 | 새 현장 범위의 P1→실제 정지·dwell→시험 녹색→P2 | 의존 조건을 통과하고 실제 이동 직전 현재 목표/경로·횟수·시간·정지/회수 수단을 확인한다. Nav2 결과·실제 정지·dwell·버튼 출발을 따로 기록한다. 정밀 XY/yaw 오차와 stop-and-go 성공을 구분한다. |
| 6 | 현재 운영 위치추정의 경사로 관측 | 승인된 구간에서 위치추정/TF·주행 상태·현재 로봇/목표 표시의 연속성을 확인한다. 기존 보행 자체와 수동 기록을 처음부터 반복하지 않는다. 후방·측면 후보는 기본 `ALL_DIRECTION_BASELINE`과 기존 `NOT_ADOPTED`를 유지한다. |

마지막 **보고된** 장비 소스 `4ff0e47467f9d049706cd70ca49af6e3da805457`는 종료된 N5의 과거 관측이다. 현재 live 값이 아니며 과거 PID·release·유휴 상태·시험창을 재사용하지 않는다. N5의 `PROCESS_MODULE_ARGUMENT` 실패 원인은 미확정이고, 보완한 프로세스 식별 도구의 새 base 실장비 검증·실제 rollback·메모리 import 경로 검증도 남아 있다. 과거 배포 helper는 다른 base에 고정되고 dashboard만 재시작하므로 새 dashboard/bridge 후보에 그대로 사용하지 않는다.

## 독립적으로 이어갈 I0 항목과 알려진 결함

- **미검증 의존 조건:** 운영 auth/mutation/source qualification owner, opaque asset codec/등록 정책, C4 genuine per-message/native identity와 costmap marking·근거 있는 clearing·재계획·actuator 경로, 실제 cone payload/model 전체 hash·측정 XYZ/자세·sensor-to-map/ground 교정·clock/receipt/TTL, C6 실제 기록과 C7 Jetson 지표. 필요한 입력 없이 `BLOCKED_AUTH`, `BLOCKED_NATIVE_IDENTITY`, `PAIRED_REAL_PRODUCER_INPUT_REQUIRED`, `UNALIGNED`, `HEIGHT_UNVERIFIED`를 해제하지 않는다.
- **알려진 기존 결함:** Maps history poll/open 경합은 결정적인 delayed-status 회귀와 최소 수리가 필요하다. 첫 통합 후보의 Ubuntu22.04 CI에서도 `global_observation_history.spec.mjs:102`의 기대 오류 대신 `IDLE · HISTORICAL_ONLY`가 관측됐다. 후속 동일 제품/browser 코드의 전체 CI 성공만으로 수리됐다고 판단하지 않는다.
- **과거 실패 기록:** I0 macOS의 관측 cancel 후 `savedLiveCenter` disabled 실패와 C4 native의 accepted/published 0 기록은 원인과 수정이 입증되지 않은 이력이다. C0 과거 2개 Node 실패·`INITIAL_GEOMETRY_PROVENANCE_REQUIRED` 실패는 최신 수정/검증과 구분해 보존한다. 과거 실패를 현재도 재현되는 통합 결함이라고 단정하지 않는다. 이번 통합의 실제 실패·수정·미해결은 MERGE_REPORT가 우선한다.

전체 기능을 단계별로 먼저 한 번씩 확인한다. 실패에는 시각·정확한 소스·증거·의존성을 기록하고 독립 항목을 계속한다. 실제 안전 문제가 있으면 그 경로를 즉시 중단하되 독립적인 비이동 검사까지 막지 않는다. 첫 결과표를 완성한 뒤 원인 분석·최소 수정·2차 비교를 수행한다. 첫 시험 중 yaw tolerance·속도·progress checker·후방 가중치를 연속 변경하지 않는다. 사용 가능한 지도/교정을 보존하고 HIGH_RESIDUAL·지도 원점·구/신 지도 정확도 연구를 다시 시작하지 않는다. A0의 모델/하위 에이전트 운영은 별도 A0 지시서를 따른다.

## 소프트웨어 재현과 복구

- 현재 통합 코드의 회귀 명령과 결과: [MERGE_REPORT](MERGE_REPORT.md). 저장소 `AGENTS.md`와 `.github/workflows/ci.yml`, `i0-offline.yml`을 기준으로 한다.
- C0 실제 ASGI 준비 패널/전체 앱 합성 도구: `tests/fixtures/planar_prior_integration/README.md`, `fixture_server.py`, `browser_probe.mjs`, `full_app_probe.mjs`, `CASE_MATRIX.md`. Linux에서 `python scripts/check_c0_prior_integration.py --output /tmp/c0-prior-review`로 실행한다. 새 출력 경로와 기존 의존성/Chromium이 필요하며 정확한 source/hash manifest 및 `PRIOR_REQUIRE_GROUPING=1`을 자동 결속한다. 센서·후보 solver·Nav2/ROS는 합성이며 실장비 성공을 증명하지 않는다.
- I0 실제 제품 합성 도구: `tests/integration_i0/fixture.py`, `cone_fixture.py`, `verify_declared_dependencies.py`, `playwright.i0.config.mjs`, `playwright.i0-cones.config.mjs`. 합성 owner 권한이나 입력을 운영 설정으로 복사하지 않는다.
- C7 독립 CLI: `python -m robot_dashboard.expansion_diagnostics --help`. 기존 한도와 snapshot을 유지해 비교하며 실제 Jetson 측정과 오프라인 결과를 구분한다.

두 archive 태그는 tracked Git 내용을 보존한다. 기존 C0 브랜치·clone·미커밋 파일·사적 증거는 그대로 유지하며, 태그가 장비 데이터나 미추적 파일 백업을 대신하지 않는다. 복구가 필요하면 태그를 새 독립 clone에서 확인하고 main에 정상 forward fix/revert를 검토한다. 기존 dirty 작업 폴더 reset, published history 재작성, force push, 태그 이동, 원본 브랜치 삭제는 하지 않는다. 장비 rollback은 현재 base·보호 자산·소유권을 확인한 별도 절차이며 이 소스 복구 기록이 실행 승인은 아니다.
