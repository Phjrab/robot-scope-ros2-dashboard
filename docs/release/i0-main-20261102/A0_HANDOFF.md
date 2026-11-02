# A0 인계 — I0 main 소스 통합, 장비 미실행

이번 인수는 검증된 I0 `ae41a9b6cf5cf5c7c133e818e3fad4693eb2053e` 전체와 main CI trigger 보완이다. C0는 병합하지 않았다. 모든 확장 기능은 기본 OFF이며 `BLOCKED_AUTH`, `BLOCKED_NATIVE_IDENTITY`, `ADVISORY_ONLY`, `DEVICE_NOT_RUN`을 유지한다. 게시 전 코드/workflow 후보 `2c9bdd15bcfe49886716bd78975886a89bfd218a`의 hosted CI 4개 job은 모두 성공했다. 최종 main/CI는 [MERGE_REPORT](MERGE_REPORT.md), [CI_COVERAGE](CI_COVERAGE.md) 및 최종 전달 receipt를 함께 확인한다.

## 인수한 기능과 기존 동작

기존 지도 목록/2D·3D 편집, URDF/현재 pose/INITIAL/GOAL 표시, Navigation·임무·STOP 경로를 유지한다. 새 확장은 `/extensions`의 별도 리뷰 화면이다. D1 전체 원본 기반 2개·3개·누적 지도 정합과 immutable 리뷰 저장, C1 계약/권한/서비스, C2 지도 UI, D2 관측 코어, D3 공식 URDF·라이선스 및 advisory 충돌 계산, C4 bounded worker, C3 기존 renderer 관측 표시, C5 범위 제한 UI helper, C6 로컬 기록 재생/비교, C7 독립 용량 진단 CLI를 인수했다.

I0 [SOURCE_LOCK](../../integration/i0/SOURCE_LOCK.json)의 258개 인수 파일과 변형 이력은 그대로 보존한다. [SOURCE_COVERAGE](SOURCE_COVERAGE.json)는 이번 후보에서 각 파일 hash를 재대조한 결과다. 팀원 ZIP을 다시 적용하거나 역할 브랜치를 중복 병합하지 않았다. 콘 후속은 동일 stamp/역행 거부, TTL·server age/transport age 보존, no-store, timeout/abort/lifecycle 정리를 포함한다. 합성 콘 5개는 표시 검증이며 실제 검출·회피가 아니다.

## 현재 flags와 한계

| 변수/경계 | 현재 기본값과 조건 |
|---|---|
| `ROBOT_SCOPE_EXPANSION_MULTIMAP` | OFF. 서버 인증·mutation 정책과 catalogue/job/store 필요 |
| `ROBOT_SCOPE_EXPANSION_SCENE` | OFF. 인증 및 별도 검증된 producer context 필요 |
| `ROBOT_SCOPE_EXPANSION_REPLAY` | OFF. 로컬 picker만 사용, 업로드·목표 재전송 없음 |
| `ROBOT_SCOPE_EXPANSION_USABILITY` | OFF. 활성 지도/관측 화면에만 적용 |
| `ROBOT_SCOPE_EXPANSION_RUNTIME` | OFF. SCENE과 명시 factory 필요; flag만으로 worker 시작 안 함 |
| CONES 표시 | 기본 OFF. 기존 구독 공유. 합성 평면·HEIGHT_UNVERIFIED |
| 운영 권한 | `BLOCKED_AUTH`; default owner의 private API 401, mutation 미설정 403 |
| native/보호 | native=false, `ADVISORY_ONLY`, `BLOCKED_NATIVE_IDENTITY` |
| asset/실측 | opaque asset decoder 미연결, 실제 cone producer·교정·clock mapping 미확보 |

값이 정확히 문자열 `1`일 때만 켜진다. 화면 노출·query/localStorage는 권한이 아니다. 실제 지도에 합성 frame을 이름만 바꿔 적용하지 않는다. 현재 지도·설정·raw PCD/bag·비밀은 이번 릴리스에 추가하지 않았다.

## C0는 중단된 미완료 checkpoint

- 유지 ref: `review/20261030-c0-3d-field-sweep`
- 고정 HEAD: `06bd98ba279e149bfecfd91007d65002d83e30b0`
- 별도 복구 tag: `archive/20261102/c0-paused-06bd98ba279e`
- [C0_OPERATOR_PRIOR_CHECKPOINT](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/06bd98ba279e149bfecfd91007d65002d83e30b0/docs/c0-field-validation/20261101/C0_OPERATOR_PRIOR_CHECKPOINT.md), 같은 디렉터리의 `C0_OPERATOR_PRIOR_CONTRACT.json`, `C1_2_OPERATOR_PRIOR_UI_CHECKPOINT.md`, `C1_4_PLANAR_PRIOR_REVIEW.md`; `docs/operator-prior-checkpoint.md`와 `tests/fixtures/planar_prior_integration/README.md`도 보존한다.
- 역할별 source: C1.1 `040cb45aef4317d7cb34695b4132e1ee8c6e7510`, C1.2 `c736f11fd2b68498c2eec62d4197d79b426b256f`, C1.3 `8217d7d2fa5c8da256dd74f400eb2e091bf2a7c0`, C1.4 `baf2de5bb62f78b247f260a69b89f1f8e96cdab7`. 모두 C0 archive의 도달 가능한 이력이다.
- [최신 C0 CI 41304523565](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41304523565): competition job 성공, Python 3.10/3.12 두 job은 JavaScript 단계 실패. 후속 browser/mission 단계 skip을 통과로 표시하지 않는다. 원격 job/step 결과는 [PRESERVED_FAILURES](PRESERVED_FAILURES.json)에 보존했다.
- checkpoint의 전수 Python 보고는 3,343건(3,341 PASS/2 optional SKIP), Node는 724건(722 PASS/2 FAIL)이다. `tests/test_camera_media.mjs:82` visibilitychange 정리와 `tests/test_control_input.mjs:257` blur fail-safe 정규식 범위 실패를 보존한다. 호출이 source에 남아 있다는 사실만으로 동작 안전성이 증명되지는 않는다.
- 새 prior ASGI↔UI 전체 통합 및 ③~④ 흐름, 최종 전체 browser, geometry 적용·Nav2/TF·INITIAL POSE 접수·연속 추정·P1/P2 주행은 미완료다. `duplicate_of` 동치군 처리가 미완료여서 복수 후보 거부가 남는다. 초기 범위 밖 전역 단일 후보/unknown gate 반례와 역할별 수정 보고를 합쳐 최종 성공으로 쓰지 않는다.
- 마지막 **보고된** 장비 배포 SHA는 `f50989a37b0203634f8dccefc4d149edafe0eadc`다. 이번에는 장비에 접속하지 않았으므로 현재 장비 상태를 확인한 값이 아니다. raw 센서·지도·사적 증거는 기존 소유자의 저장 위치에 남으며 새 Git archive가 미추적 파일까지 보존한다는 뜻은 아니다.

## A0 우선 작업

1. C0 archive에서 최신 통합 snapshot을 고정해 실패 2건의 실제 이벤트 순서·예외 경로를 검증하고, prior 범위/조건부 proof/TTL/단회 사용/중복 후보 및 ASGI↔UI 전체 흐름을 재검증한다. 그 후 필요한 변경만 선택 인수한다. C0 전체 병합이나 과거 app/navigation 파일 덮어쓰기는 하지 않는다.
2. 운영 auth/mutation/source qualification owner를 정한다. I0의 세 공유 hook과 최신 C0 지도 pairing·height/tilt·source/session/generation·관측 ownership·STOP/lease 경계를 수동 대조한다. 이전 [C0_RECONCILIATION](../../integration/i0/C0_RECONCILIATION.md)은 당시 snapshot의 기록이며 최신 C0 전체와 같다고 가정하지 않는다.
3. C4 genuine per-message identity 또는 검토된 Humble graph evidence 계약을 먼저 확보한다. `OWNER_SOURCE_IDENTITY_UNAVAILABLE`, `GRAPH_ENDPOINT_CONTRACT_UNAVAILABLE`, QoS UNKNOWN/history=0를 원하는 값으로 덮지 않는다. 이어 기존 D3 native 환경에서 marking, 근거 있는 clearing, planner 변화, stale/epoch/late frame, 실제 simulated actuator까지 별도 검증한다.
4. C4 원본 실패 기록: archive `archive/20261102/x-c4-b7242fca7c1b`의 `docs/parallel-expansion-20261029/C4/ROS_ADAPTER.md`, `ROS_EVIDENCE.json`. [native 41035596751](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41035596751)는 62 callbacks/accepted 0/published 0으로 실패했다. [표준 CI 41035596779](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41035596779)의 Ubuntu 24.04 browser download timeout도 별도 미해결 기록이다. 원래 D3 native 5개 기록 재생을 C4 end-to-end 성공으로 바꾸지 않는다.
5. opaque asset codec/등록 정책, 실제 cone payload·model full hash·측정 XYZ/자세·sensor-to-map/ground 교정·clock/receipt/TTL·Jetson 부하를 확보한다. 현재 `PAIRED_REAL_PRODUCER_INPUT_REQUIRED`, `UNALIGNED`, `HEIGHT_UNVERIFIED`는 해결되지 않았다.
6. 기존 Maps history poll/open 경합을 결정적 delayed-status 회귀로 수리한다. 전체 browser 성공만으로 기존 결함이 해결됐다고 판단하지 않는다.
7. 이번 macOS 회귀의 `tests/e2e/live_observation.spec.mjs:788`(cancel 후 `savedLiveCenter`, assertion :809) 실패도 보존한다. I0와 동일한 코드/테스트에서 관찰했으며 원인·재현 조건을 확정하지 않았다. hosted CI 결과와 별도로 추적하고 timeout/assertion을 완화하지 않는다.

## 보존과 복구

사용자는 다른 기기 상태를 모른다고 답했고 불확실한 ref 유지를 요청했다. 따라서 I0와 D1–D3/C1–C7 11개 후보는 `ARCHIVE_ONLY`, C0는 `KEEP`다. 원격 ref 삭제 0, 로컬 branch/worktree/clone/증거 삭제 0이다. [BRANCH_RETIREMENT](BRANCH_RETIREMENT.json)의 개별 이유·태그·복구 recipe를 따른다. 원격 ref가 남아 있어도 archive를 재지정하지 않는다.

복구는 새 로컬 이름으로 `git fetch origin tag <archive-tag>` 후 `git branch <new-name> <archive-tag>^{commit}`를 사용한다. 기존 dirty checkout을 reset하지 않는다. main 소스 복구가 필요하면 검토된 forward fix/revert를 쓰고 force-push하지 않는다. 복구 tag는 배포나 주행 승인이 아니다.

이번 실행의 로봇 접속·배포·서비스/지도/설정 변경·ROS 제어·주행은 모두 0회다. **DEVICE_NOT_RUN**.
