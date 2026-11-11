# 주행 탭 검증 상태 — 2026-11-11 (KST)

## 최신 현장 상태

장비 코드 `75dc813`: 지도 조합 확인 후 정지 센서 관측 **93.305초 / 46표본 READY**,
신선한 자세·점군 준비 검사 통과. Nav2 상태 조회의 파일 검사 중 작업 잠금 충돌을
수정했고, 배포 시 누락된 공용 ROS 빌드 연결도 복구했다. 시험 후 관측은 정상 종료,
STOP 잠금·lease 없음·Move 0건을 확인했다. 최초 두 후보의 재발은 실패 이력으로 남긴다.

다음은 현재 사용자 위치·방향 초안 재확인과 지도 기준 높이·기울기 제안 검증이다.
Nav2 시작, 초기 위치 전송, 지도 정합, 실제 목표 이동은 **NOT_RUN**이며,
진행률 첫 feedback 결함은 **미수정**이다. [최신 인계](HANDOFF.md)와
[상세 원인·검증](../../coordination/C0_OBSERVATION_OWNER_SAMPLING_20261109.md)을 우선한다.
아래 표와 세션별 내용은 이전 시점의 보존 이력이다.

범위는 `#navigation`의 **주행 → Nav2 자율주행** 전체와 지도·위치추정·Nav2·제어 공통 백엔드다.
`#experiments` A3는 제외한다. 자동 미션·녹색 출발·새 경로 계획 기능·확장 메뉴·VSLAM·새 odometry·강화학습을 선행 과제로 추가하지 않는다.

인수 기준은 최신 `origin/main` **4b244d4024327c070482cdd71f4732ea081962d7**이다.
처음 인수한 main은 clean이었으며 참고 SHA보다 최신 커밋은 없었다. 브랜치/worktree/PR을 만들지 않았다.
지도 연결·관측 소유권 변경은 이미 통합된 현재 구현을 사용한다.

## 화면 6단계 (내부 7개 검사를 화면 순서로 합침)

`구현 있음`은 현장 완료 판정이 아니다. 이 세션에서 장비 상태를 읽지 않았으므로 **현재 로봇 단계는 미확인**이다.
아래 native·정지·이동 열은 모두 **이번 세션, 이 후보 소스** 기준이다.

| 화면 단계 | 구현 완료 여부 | 단위/fixture 검증 | 실제 ROS/Nav2 | 현재 장비 정지 검증 | 실제 목표 이동 | 첫 미확인/실패와 다음 작업 |
|---|---|---|---|---|---|---|
| ① 지도 연결·사용자 위치 초안 | 기존 구현 있음: 명시 좌표관계 확인, ID/revision 고정, 초안 무효화 | 준비/초안 브라우저, map pair·API 회귀. UNKNOWN/OCCUPIED는 현재 실패 아님 | NOT_RUN | NOT_RUN | NOT_RUN | 실제 실행본·mode/profile·선택 지도·교정 hash부터 읽는다. 사용자 좌표관계 확인은 실측 정합이 아님 |
| ② 센서·교정·초기값 준비 | 기존 구현 + 이번 강제 refresh 유실/늦은 응답 수정 | UI 차단·명령 POST 없음·실제 ASGI admission 409, 정확한 session 종료 회귀 | NOT_RUN | NOT_RUN | NOT_RUN | 장비의 bridge capability·소유권·STOP·센서 출처/신선도 미확인. 승인된 정지 관측 창에서 확인 |
| ③ Nav2 시작·노드와 TF 확인 | 기존 source/job/세대·readiness 검사 있음 | gateway·coordinator·준비/health/event safety 회귀 | NOT_RUN | NOT_RUN | NOT_RUN | 실제 실행본에서 노드 lifecycle, source·TF 시각/방향·유일 publisher 확인 |
| ④ INITIAL POSE 접수·지도 정합 | 기존 명시 접수/별도 match 및 품질 검사 있음 | 운영 위치추정·handoff·늦은 receipt/다른 세대 거절 회귀 | NOT_RUN | NOT_RUN | NOT_RUN | 명시 위치의 이번 실행 접수 후 별도 저장지도 정합. HTTP 200·마커·MATCH_ARMED만으로 완료 금지 |
| ⑤ 추정 위치·주행 준비 확인 | 기존 지속 보정·품질·Nav2 소비·안전 gate 있음 | runtime/gateway·stale·source mismatch 회귀 | NOT_RUN | NOT_RUN | NOT_RUN | 신선한 연속 correction과 동일 실행의 Nav2 TF 소비 확인. 모의 TF를 native 통과로 사용하지 않음 |
| ⑥ 목표 전송·경로 진행 | 기존 전송·취소·STOP 있음. **작은 양의 첫 feedback 진행률 결함 미해결** | 최신 gateway 실행 재현, 정상/정체/zero/noise/reverse/새 goal/취소/재시작 대조 | NOT_RUN | NOT_RUN | NOT_RUN | 새 goal과 그 내부 plan/feedback의 연결 근거를 보강해야 함. 이후 승인된 짧은 목표·취소/STOP·측정 정지·정지 후 XY/yaw·다음 명시 목표 순서 |

구체 실행 결과와 환경 한계는 [TEST_RESULTS.md](TEST_RESULTS.md), 현장 순서는 [FIELD_PLAN.md](FIELD_PLAN.md)에 있다.

## 모드 구분

장비의 `GET /api/v1/navigation`에서 `mode`, `pipeline.mode`, `session_mode`,
`bindings.navigation_profile`, 실제 `operational_localization`을 함께 읽는다.
`GET /api/v1/navigation/operational-3d/preparation-inputs`의 `operational_state.activation`,
selected pins/generation과 실제 실행 source를 대조한다.

- 기존 2D: 준비 선택의 `LEGACY_2D`만으로 현재 실행을 단정하지 않는다. 실제 standard mode/profile/source를 함께 확인한다.
- 저장 3D: 선택의 `NEXT_NAVIGATION_START`는 다음 시작용 구성이다. 실행된 `STORED_PCD_FASTLIO`, 지도 revision, job/bundle/localization/runtime 세대가 일치해야 실제 적용으로 기록한다.
- `manual_seeded_2d`/A3이면 이번 검증에서 멈추고 범위 밖으로 기록한다. 다른 모드로 자동 전환하지 않는다.

## 서로 다른 미해결 문제

1. **진행률/health 계산:** 최신 소스에서 소프트웨어 재현됨. `.0416856`을 즉시 baseline으로 채택하면 이후 `.838 → … → .490`에도 표시 계산이 0이다. 수치가 증가했다는 이유만으로 baseline을 reset하거나 stall 제한을 늘리지 않았다.
2. **실제 저속 접근 정체:** 10월 30일 별도 현장 이력이다. 이번 장비 재현 NOT_RUN. 표시 결함이 실제 접근을 중단시켰다고 주장하지 않는다.
3. **action 성공 후 정지 방향 잔차:** 같은 날의 별도 현장 이력이다. SUCCEEDED와 물리 정지/정밀 도착은 별도다. 이번 yaw 설정 변경·시험 NOT_RUN.

현재 전체의 첫 현장 미확인은 실행본·모드·지도·교정·정지 상태 인수다. 과거 시험창·목표·배포 승인과 과거 A3 native 결과는 이번 승인/통과로 재사용하지 않는다.


## 후속 2회차 — 2026-11-11, 488d279 인수

기준 `488d279b3a97300db80fd32843008b3e83344c5a`는 이번 인수 시 원격 main과
일치했고 새 일반 main 체크아웃은 clean이었다. 상위 작업 폴더에 남아 있는 과거
체크아웃과 미커밋 변경은 보존했다. branch/worktree/PR 생성·과거 역할 병합 없음.
기준 CI 42998127916 및 I0 42998127664의 success를 GitHub에서 다시 확인했다.

이번 변경은 **오프라인 진단 도구와 회귀 검사**다. 운영 gateway/health/UI의 진행률
결함을 수정한 후보가 아니다. 표시/health 결함은 여전히 SOFTWARE_REPRODUCED다.
실제 저속 정체와 action 성공 후 정지 yaw 잔차는 별도 미검증 항목으로 유지한다.

| 화면 단계 | 구현 / 이번 단위·fixture | 실제 ROS/Nav2 | 현재 장비 정지 | 실제 목표 이동 | 이번 첫 미확인 / 다음 작업 |
|---|---|---|---|---|---|
| ① 지도 연결·사용자 위치 초안 | 기존 구현 유지; 기존 브라우저 회귀 대상 | NOT_RUN | UNKNOWN | NOT_RUN | 장비 실행본·실제 모드·지도 pins 읽기 |
| ② 센서·교정·초기값 준비 | 090afc7 수정 유지; 강제 refresh·exact stop·unsupported admission 회귀 대상 | NOT_RUN | UNKNOWN | NOT_RUN | bridge capability·STOP·lease·센서 신선도 미확인 |
| ③ Nav2 시작·노드와 TF 확인 | 기존 구현 유지; 전체 소프트웨어 회귀 대상 | NOT_RUN | UNKNOWN | NOT_RUN | native 노드/source/TF 미확인 |
| ④ INITIAL POSE 접수·지도 정합 | 기존 명시 접수와 별도 match 기준 유지 | NOT_RUN | UNKNOWN | NOT_RUN | 이번 실행의 pose receipt와 정합 증거 없음 |
| ⑤ 추정 위치·주행 준비 확인 | 기존 freshness·품질·소비·안전 gate 유지 | NOT_RUN | UNKNOWN | NOT_RUN | 지속 correction과 Nav2 소비 증거 없음 |
| ⑥ 목표 전송·경로 진행 | 진단 확장: matching plan 뒤에도 재현, 짧은 정상 목표·큰 왕복 대조, 부분 재현 종료코드 수정 | NOT_RUN | UNKNOWN | NOT_RUN | feedback 생산자가 소비한 goal/plan 문맥 필요; 임의 baseline reset 미적용 |

과거 인계의 장비 주소에 GET 1회와 host key 검증을 유지한 BatchMode SSH 1회를
시도했으나 모두 timeout이었다. 장비 전원 상태·오프라인 여부를 판정할 수 없다.
실제 mode/profile/source를 받지 못했으므로 2D/저장 3D/A3 어느 모드도 추정하지 않았다.
[진행률 후속 조사](FOLLOWUP_2_PROGRESS_CONTEXT.md)와 아래 후속 실행 기록을 함께 읽는다.


후속 게시 검사에서 추가 발견: a3f50c7 일반 CI 7 jobs success, I0는 동일 위치에서
2회 failure. 로컬 동일 probe는 통과했지만 그 원격 실패를 없었던 것으로 취급하지 않는다.
동일 predicate를 드물게 표본화해 짧은 유효 창을 놓치는 경로를 별도로 재현하여
probe 관측 방식을 수정했다. ② 운영 조건/1초 freshness/2초 제품 poll/5초 검사 제한은
바꾸지 않았다. 상세 증거와 후속 후보 결과는 TEST_RESULTS/HANDOFF 후속 절을 따른다.
