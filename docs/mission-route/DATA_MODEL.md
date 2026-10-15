# 정의·방문·실행 데이터

적용 source: `22c7913c879afcca536a78d552dcdf98f0f53098`. 실제 제품 코드/소프트웨어 검증 결과는 `PROGRESS.md`, `VALIDATION.json`을 따른다.

## 객체와 revision

| 객체 | 의미 / 저장 |
|---|---|
| SpatialRoute | 기존 E1 geometry·policy·revision. MR은 원본을 수정하지 않고 exact `route_ref`로 참조 |
| MissionDefinition | label, map family, annotation revision, mode, 1~32 visits, optional route ref. canonical JSON SHA-256 semantic revision |
| Validation/Preview | 해당 definition/map/annotation/route/context/planner/footprint pin의 검사 결과. 실행 권한 없음 |
| MissionRun | 새 기존 coordinator id + 정의 snapshot/revision + pin + 생성/실행/종료 시각 + 결과/관측 이력 |

기존 미션 store와 별개인 `mission-plans-v1.json`을 사용한다. legacy annotation 미션 원본에 가짜 annotation을 추가하지 않는다. 정의 PATCH는 `base_revision` CAS이며 active run이 참조하는 정의는 `DEFINITION_ACTIVE_COPY_REQUIRED`로 새 복사를 요구한다. 정의 DELETE도 exact revision과 idle 상태를 확인하고 historical run은 보존한다. 동일 정의로 다시 실행하려면 새 run을 만든다.

## 방문 설정

- `visit_id`: 32자리 hex, 정의 안에서 유일. 같은 annotation을 두 번 방문해도 별도 id다.
- target: `annotation_ref`이면 annotation_id만, `mission_local_pose`이면 pose만 허용한다. pose는 meter/radian, finite x/y ±10000, yaw ±π다.
- `kind`: STOP/TASK 실행 지원 범위. PASS_THROUGH는 저장 가능하지만 실행 차단.
- label: 공백 정리 후 1~64자. `hold_seconds`: 0~300초, 몰래 clamp하지 않는다.
- `requires_operator_confirmation`: 접근 전 확인. `after_arrival_confirmation`: 도착·대기 후 확인. 서로 독립이다.
- `speed`: DEFAULT만 effective. SLOW/NORMAL은 저장 후 미지원 차단.
- `arrival_tolerance`: null이면 NAV2_DEFAULT. 0.05~2m 요청값을 저장할 수 있지만 per-visit override는 실제 실행 지원 전까지 차단한다.
- `action`: none만 실행. photo/sit_then_rise/dock은 `ACTION_UNAVAILABLE`.

mission-local yaw는 기존 `send_goal`로 전달된다. annotation target은 기본적으로 pinned annotation yaw를 상속하고 nullable `heading_yaw`가 있으면 방문별 방향만 override한다. override는 annotation target에만 허용되며 exact annotation의 x/y를 읽어 override yaw와 함께 기존 `send_goal`로 전달한다. 저장→compile→dispatch 전달은 synthetic navigation test로 PASS했다. 방문별 방향 override·다음 구간 방향 UI와 stale 주석 재연결은 최종 Chromium fixture에서도 검증했다.

## API

additive route 20개를 구현했다.

| 경로 | 의미 |
|---|---|
| GET/POST `/api/v1/mission-plans` | 정의 목록/context 읽기, 새 정의 저장 |
| GET/PATCH `/api/v1/mission-plans/{id}` | 조회, CAS 수정 |
| DELETE `/api/v1/mission-plans/{id}` | exact revision CAS 삭제, active 정의 거부, 이력 보존 |
| POST `.../{id}/copy` | 새 id 복사 |
| POST `.../{id}/validate` | 작성 검사 |
| POST `.../{id}/plan-preview` | 실제 planner 요청; 기본 자원 gate 비활성 |
| POST `.../{id}/compile` | idempotent 실행 초안, `start_sent=false` |
| GET `/api/v1/mission-route-drafts/{route_id}` | E1 경로를 검토 가능한 STOP 초안으로 투영 |
| POST `.../{id}/runs` | 새 run 생성; goal 없음 |
| GET `/api/v1/mission-runs[/{id}]` | 이력/현재 coordinator 상태 |
| GET `/api/v1/mission-runs/{id}/export` | allowlist 이력 export, confirmation token 제외, executable=false |
| POST `.../{run_id}/{start,pause,resume,retry,skip,abort}` | 고정 allowlist 실행 요청 |

mutation에는 same-origin과 기존 competition gate를 적용한다. strict Pydantic schema가 extra field, NaN/Inf, 잘못된 id/수량을 거부한다. 임의 topic/action/plugin/script/host path를 받지 않는다. preview start는 `current_operational_pose` 또는 explicit `hypothetical_preview_start`이며 후자는 실행 시작에 재사용하지 않는다.

## idempotency와 저장 보장

request_id는 16~64자 allowlist다. 같은 key/같은 digest의 일반 데이터 요청은 이전 결과를 반환하고 다른 payload는 conflict다. run 생성·실행 결과는 전체 이력을 복제하지 않고 bounded `run_ref` receipt로 저장한다. 같은 요청 재전송은 같은 run의 현재 상태를 읽어 반환하며 goal·작업을 재전송하지 않는다. 실행 전 ledger에 pending 결과를 저장하고 결과를 못 확정한 요청은 `REQUEST_OUTCOME_UNCERTAIN`으로 남긴다. 새 key로 자동 재전송하지 않는다. 외부 side effect의 exactly-once 보장은 하지 않는다.

pause/abort는 정지에 필요한 예외 경로다. ledger가 가득 찼거나 저장이 실패해도 소유 goal 정리를 수행하며 `STOP_APPLIED_WITHOUT_DURABLE_REQUEST_RECEIPT` 또는 `STOP_APPLIED_WITHOUT_DURABLE_HISTORY` audit warning을 반환한다. 기록 내구성을 확인한 것처럼 표시하지 않는다. 이 예외를 start/resume/retry/skip에 적용하지 않는다.

기존 private store 구현을 재사용해 root 0700, 파일 0600, 소유자·symlink 검사, bounded JSON, atomic replace와 fsync를 적용한다. 정의 64개, run 32개, request ledger 256개, 파일 512KiB 상한이다. 상한에서는 명시 conflict이며 active 이력을 자동 삭제하지 않는다. corruption은 원본 보존 후 unavailable로 처리한다.

read-only run export는 `mission-history.v1`, `executable=false`이며 allowlist 필드만 포함한다. 운영 데이터 migration/import/자동 archive는 없다. run의 `source_sha`/`runtime_sha`는 null로 저장하며 실제 build identity를 확보했다고 주장하지 않는다. 신규 waypoint 필드가 기존 coordinator 저장 형식에 추가되므로 이전 source의 strict reader와 호환 여부를 먼저 검사해야 한다. source revert와 data restore는 별개이며 실제 데이터 변환·rollback을 수행하지 않았다.

## 테스트 근거

focused83 및 전체 Python1939(skip2/fail0), Node381·Chromium96 PASS. CAS/idempotency/immutable snapshot, copy/delete 이력 보존, token-free export, strict 입력·private store·corrupt/symlink·크기 상한, compile 무동작과 설정의 실행 전달을 실제 코드에 synthetic navigation provider를 넣어 검증했다. 상세 로그·hash·시각은 VALIDATION.json이다. native/장비 결과가 아니다.
