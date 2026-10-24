# 대회 미션 UI·계약 HANDOFF — 2026-10-24

시작 기준: `main@4f77133`, 최종 통합 기준: `main@1cddada` (VM 산출물 공개 포함). 문서의 `c00cc585` 이후 최신 main에서 구현했다. 기존 다른 체크아웃의 미커밋 관측 기능 변경과 UI 브랜치는 건드리지 않았다. 이 문서는 구현 인계이며 장비 배포·서비스 재시작·카메라 인수·ARM·initialpose·goal·이동 승인이 아니다.

## 현재 가능한 것

- 기존 `#missions`의 경로·미션 작업공간, E1 geometry/지도·주석 선택, CAS 저장, request ledger, 기존 미션·NavigationCoordinator와 coordination lock을 유지했다.
- 편집 / 검사 / 실행 / 기록, 순서·좌표 미확정 DRAFT 6단계(장애물, 신호 1, terrain, 신호 2, 주차, OUT), 단계별 설정/차단 원인, 서버 snapshot 타이머·event log를 제공한다.
- 모든 step/visit은 별도 ID다. 동일 zone 복제도 새 ID를 만든다. DRAFT 좌표는 `unplaced`/null이며 지도 편집기로 명시적으로 배치한다. 이 순서는 규정 확정 경로가 아니다.
- `NAVIGATE_ADAPTIVE`, `TRAFFIC_STOP_AND_GO`, `TRAVERSE_TERRAIN`, `PARK_SIT_HOLD`, `FINISH_CROSSING`을 versioned `mission_action`으로 저장한다. 기존 `arrival_action`의 뜻이나 실행 제한은 변경하지 않았다.
- 실장비 action adapter는 **모두 UNCONNECTED**. 단계별 요구 capability를 구분한다. 신호 detector/발 evidence/물리정지/arbiter, terrain gait, posture/full containment/full crossing은 별도다. VM 소스·검증 산출물을 읽기 전용 adapter로 연결했다. VM 합성 검증과 실장비 연결 상태를 별도 표시한다.
- 명시적인 fixture 시도 생성/시작/취소와 읽기 전용 export가 가능하다. fixture 완료는 실제 주행/카메라/앞발 판정/실제 지도 경로의 증거가 아니다. `PRESENT`는 fixture 코드의 존재만 의미한다.
- Cockpit 미션 카드는 요약·PAUSE/ABORT·경로·미션 링크만 제공한다. 기존 주석 미션 편집기는 전용 화면의 고급 메뉴에 남아 있다.

## 코드 소유·통합 지점

| 파일 | 책임 |
| --- | --- |
| `mission_routes/models.py` | legacy 읽기/직렬화 보존, versioned action·대회 metadata·엄격한 최소시간 검증 |
| `mission_routes/competition_assets.py`, `static/features/mission_route/arena_preview.js` | VM checksum·semantic manifest adapter와 실제 GLB 설계 뷰. 임의 경로·카메라·실측 overlay 없음 |
| `mission_routes/competition_contract.py` | PROPOSED action registry, step별 capability, 모델 manifest alignment projection, trusted observation DTO |
| `mission_routes/competition_executor.py` | 서버 monotonic 기반 **fixture 전용** action orchestration과 adapter receipt log; ROS/카메라/bridge 참조 없음 |
| `mission_routes/service.py`, `api/routers/mission_routes.py` | 기존 저장소·CAS·ledger·이력에 additive fixture API 연결, native 실행 차단 |
| `static/features/mission_route/competition.js`, `workspace.js` | 기존 UI 안의 대회 편집·상태·fixture/원본 증거 구분 |
| `app.py`, `mission_routes/wiring.py` | 종료 시 fixture task close hook 추가. startup·로봇 owner 생성 변경 없음 |

이 패치의 공용 파일 적용 담당은 Codex 미션이다. 다음 통합 담당은 VM patch를 검토하여 **한 adapter 경계**에서 정규화하고 공용 파일 충돌을 조정해야 한다. 모델/회피/YOLO 알고리즘, camera owner, command bridge, Nav2 profile 생성기를 구현하거나 교체하지 않았다.

신규 API는 다음 다섯 개다. 읽기 API는 로봇 owner를 만들지 않는다. fixture 생성은 기존 same-origin/competition lock/정의 revision/request-id ledger를 사용한다. 시작·취소·snapshot·export는 기존 `mission-runs` 경로를 재사용한다.

| 메서드·경로 | 결과 |
| --- | --- |
| GET `/api/v1/mission-competition/capabilities` | action별 native 미연결 사유와 분리된 VM 합성 evidence |
| GET `/api/v1/mission-competition/template` | 새 visit/step ID가 있는 좌표 미지정 DRAFT |
| GET `/api/v1/mission-competition/arena` | checksum 확인한 manifest와 정합 미확인 상태 |
| GET `/api/v1/mission-competition/arena/asset` | 고정 allowlist의 GLB만 제공; 불일치 시 503 |
| POST `/api/v1/mission-plans/{id}/fixture-runs` | `request_id`, `revision`, `scenario`로 합성 시도 생성; 시작은 별도 요청 |

## 공통 계약 v0.1 대비 차이 — 모두 PROPOSED

1. `DefinitionInput.competition`과 `Visit.mission_action`은 선택적 namespaced 필드다. `competition.v0.1`, `mission-action.v0.1`을 명시한다. 정의 map/annotation/route pin에 arena/model/profile/rules revision을 더해 run snapshot에 고정한다.
2. 기존 기본 `action`, `speed`, `arrival_tolerance`, `hold_seconds`는 그대로다. 대회 정의는 legacy action/hold/중간 운영자 확인과 혼합할 수 없다. `dwell_seconds >= 2`, `sit_seconds >= 5`를 HTTP/Pydantic에서 검증한다. REVIEWED에는 모든 방문 좌표와 명시적인 revision이 필요하지만, REVIEWED 자체로 실행이 활성화되지는 않는다.
3. `competition-evidence.v0.1`은 VM의 `SignalObservation`, `StopZoneObservation`, `RouteStatus`를 하나로 정규화할 **제안 adapter 입력**이다. 기존 ROS msg/API라고 주장하지 않는다. 현재 fixture만 생성하며 공개 observation POST나 manual GREEN API는 없다.
4. envelope에 `source_age_s`를 둔다. 현재 fixture의 source clock만 허용한다. native adapter는 시계 동기·component별 source age·receipt age를 검증한 후에만 조합해야 한다. 서로 다른 호스트 monotonic을 빼면 안 된다. `source_stamp_ns`는 문자열이고 수신 monotonic은 wire에 노출하지 않는다.
5. producer epoch/sequence, owner/run/step/goal/generation/config hash가 맞지 않는 결과는 dwell을 초기화하고 전이를 차단한다. fixture freshness/최대 연속 evidence gap은 **0.5초**이며 gap 발생 시 누적을 새로 시작한다. production의 센서 cadence에 맞는 gap 정책은 별도 검토 대상이다.
6. fixture `MotionConstraint`는 receipt log일 뿐 제어 명령이 아니다. HOLD에는 owner/run/step/request/generation, 0 caps, current-generation validity를 넣는다. native arbiter에서는 E-stop/충돌 > 신호·미션 HOLD > terrain cap > tracking, 가장 제한적인 합성, stale 비제로 명령 비재생을 구현·검증해야 한다. RELEASE만으로 주행 허가가 되면 안 된다.
7. native registry 등록 경로는 아직 없다. **fixture adapter를 native에 연결하거나 mode 문자열만 바꾸지 말 것.** 기존 MissionCoordinator의 shared lock/admission/goal ownership/cancel ACK를 사용하는 통합 adapter가 별도로 필요하다. fixture는 hardware ownership을 주장하지 않는다.

기계 판독용 DTO: `definition.schema.json`, `evidence.schema.json`. 명시적 입력 fixture: `tests/fixtures/mission_competition/draft-v0.1.json`.

## 실행·관측 의미

브라우저는 정의 편집, 명시적 시작/취소 요청, server snapshot 조회만 한다. 서버 background task가 timer·행동 상태를 소유한다. 화면 이동/refresh/close는 timer를 중단하거나 새로 시작하지 않는다. 재접속은 저장된 run을 읽으며 자동 start가 없다. 서버 재시작/정상 종료 시 진행 중 fixture는 INTERRUPTED이고 green/dwell/goal/constraint는 복원되지 않는다. 새 시도가 필요하다.

신호 step은 접근 goal의 SUCCEEDED 또는 CANCELED+ACK를 받은 다음 HOLD를 요청하고 HOLD ACK·앞발 두 개·physical STOP을 확인한다. 유효 조건 연속시간 2초 이상 + 연결된 fresh GREEN + clear path + 현재 pose에서만 RELEASE receipt와 새 exit goal generation을 만든다. RED/UNKNOWN/다른 신호/발 하나/PROXY/카메라 stale/pose 없음은 서로 다른 사유로 차단한다. 5초 신호 주기는 안내만 하고 GREEN을 예측하지 않는다.

의도된 `HOLD_SIGNAL`은 `WAIT_OBSTACLE`과 구분하며 이전 접근 goal의 Nav2 progress 결과로 recovery를 호출하지 않는다. 접근 중 FAILED는 `NAVIGATION_PROGRESS_FAILED`, signal timeout은 `SIGNAL_WAIT_TIMEOUT`이다. fixture는 costmap clear/spin/backup이나 velocity를 보내지 않는다. 실제 신호 HOLD 중 command producer가 멈추는지는 VM/온보드 arbiter 통합에서 별도로 증명해야 한다.

주차는 전체 포함 + SIT + STOP 확인 후 연속 5초다. terrain은 executor completion, OUT은 full-body-crossed evidence가 필요하다. 앉은 뒤 다음 이동을 위한 자세 전환도 VM의 검증된 posture/gait executor가 담당해야 한다.

원본 RGB ROI/bbox/native size, processed/mask handle, exposure/quality/raw/stable/confidence, 발 evidence, physical stop을 별도 표시한다. 현재 이미지 공급자는 미연결이며 합성 관측에 카메라 이미지를 만들어 넣지 않는다. UI가 색을 분류하지 않는다. native/fixture 계획은 서로 다른 스타일·data-evidence로 구분한다. 미관측 path·궤적·거리·ETA·clearance는 비어 있거나 null이다.

## 모델/센서/행동 VM 산출물이 필요한 부분

- 공개된 `rulebook-20261015-v1` semantic manifest와 GLB를 연결했다. checksum 검증 후 실제 GLB vertices/indices/material/node transform으로 설계 뷰를 그린다. 외부 URL/임의 파일 경로/원격 로더가 없다. 현재 bundle의 `map_transform=null`, course graph DRAFT를 그대로 유지하여 pose overlay를 허용하지 않는다. GLB 존재·무결성은 정합 증거가 아니다. design Z-up과 GLB Y-up을 분리하며 알려진 삼각형 scene 이외의 extensions/hierarchy는 모델 adapter 갱신을 요구한다. 추후 overlay에는 정확한 map+arena revision과 검증된 rigid T_map_arena_design이 필요하다.
- 현재 장애물 metric geometry와 실제 Nav2 path provider는 미연결이다. 기존 지도 obstacle을 novelty=false라는 이유로 collision에서 제외하지 말 것. ROI bbox로 metric geometry를 만들지 말 것.
- YOLO ROI/raw/processed image handle, source stamp/epoch/sequence/model hash, stable signal·crossing association, quality와 component별 freshness가 필요하다.
- 실제 두 앞발·정지·몸체 완전 포함/통과 evidence, 검증된 gait/posture executor, 단일 arbiter ACK, 신선한 exit leg dispatch가 필요하다. fixture의 SIM_GT를 실측 판정으로 승격하지 말 것.
- stage는 PRESENT → VM_VERIFIED → ROBOT_OBSERVED → ROBOT_QUALIFIED와 mode를 별도로 기록해야 한다. 현재 native 연결은 UNCONNECTED다. VM `core.py`/adapter checksum과 공개 검증 보고에 근거한 `vm_evidence`는 `SYNTHETIC_ONLY`로 분리한다. detector는 ADAPTER_IMPLEMENTED/INPUT_REQUIRED, color/FSM은 VM_SYNTHETIC_VERIFIED, feet는 CANDIDATE_GEOMETRY_ONLY, native Nav2·Jetson·real RGB는 NOT_RUN이다. 이번 미션 작업은 OpenCV/YOLO를 가져오거나 다시 구현하지 않았다.
- 정비 최대 2회/총시간 포함/재개위치 규정은 metadata와 이력 export에 보존한다. 실제 정비 절차·공식 점수 산정은 구현하지 않았다. 자율 실행 중 운영자 확인이나 원격 step skip에 의존하는 경로는 없다.

## 저장·롤백

기존 `mission-plans.v1` 저장소와 private/atomic/bounded 규칙, request ledger를 재사용한다. 새 선택 필드가 없는 기존 정의는 원래 JSON shape와 digest를 유지하며 읽을 때 자동 migration하지 않는다. legacy MissionCoordinator 저장소도 변경하지 않는다. 대회 템플릿은 기존 미션을 덮어쓰지 않고 새 정의 사본으로 저장한다. active 정의 수정은 거부되며 복사가 필요하다. 기존 run의 definition/pins는 불변이다.

구버전 앱으로 롤백할 때 새 선택 필드는 구버전 validator가 거부할 수 있다. 배포 전 두 저장소의 private backup을 만들고, 구버전에는 해당 구버전 backup을 **명시적으로** 복원해야 한다. 실행 이력을 executable resume 데이터로 import하지 않는다. 이번 작업은 실제 저장소 migration·장비 데이터 변경을 수행하지 않았다.

## 검증 재현

```sh
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
npx playwright test tests/e2e/mission_route.spec.mjs tests/e2e/mission_page.spec.mjs
npx playwright test --config playwright.competition.config.mjs
```

`tests/competition_fixture_server.py`는 실제 Python API/PlanStore를 임시 폴더에서 사용하며 production app을 import하지 않는다. navigation fixture는 실제 goal/cancel 호출을 AssertionError로 거부한다. `playwright.competition.config.mjs`는 localhost:4187(또는 `COMPETITION_FIXTURE_PORT`)을 사용한다. 포트가 사용 중이면 기존 서버를 재사용하거나 종료하지 않고 실패한다. 브라우저를 닫고 새 탭으로 접속하는 테스트에서 서버 progression과 완료를 확인한다.

최종 실행 결과는 `VALIDATION.md`에 기록한다. 전체 suite에 포함된 기존 LiDAR/VSLAM/지도 편집/STOP·UI 단위 검사와 기존 미션 mobile/theme/zoom smoke를 함께 수행한다. 로봇 실측·주행 검증은 이번 결과에 포함되지 않는다.

## 이번에 반영한 VM 인계의 제약

`1cddada`의 traffic/avoidance/integration HANDOFF를 검토했다. VM traffic FSM의 APPROACH HOLD는 접근 goal을 스스로 막을 수 있으므로 현 미션 fixture처럼 **접근 terminal/cancel ACK 이후** 활성화해야 한다. VM arbiter adapter TTL은 기본 0.25초이고 현재 mission fixture evidence gap은 0.5초로 서로 다르다. `MotionConstraint.validity`도 VM은 `receipt_ttl_s`, 본 fixture는 `current_generation_only` receipt이므로 자동 wire 호환으로 취급하지 않는다. 다음 native 통합은 fresh receiver sequence/TTL/retired epoch/command barrier와 실제 departure evidence를 한 adapter에서 조정해야 한다. 기존 실험 코드는 수정하지 않았고 native execution을 활성화하지 않았다.
