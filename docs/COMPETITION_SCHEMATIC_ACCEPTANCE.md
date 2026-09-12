# 도식 수동 안내 — 로컬 검증 및 인계

초기 검증일: 2026-09-12 (KST). 초기 검증 기준 HEAD:
`78224f45c8ddec13ff5f99df6c476ccc292f9929`.

초기 로컬 구현 단계에서는 사용자 지시에 따라 **커밋·푸시·Go2/Jetson 접속·배포·서비스 재시작을 하지 않았다.**
실제 로봇 명령, Nav2 목표/초기 위치, Mission 생성·실행·내보내기도 하지 않았다.
검증은 임시 로컬 데이터와 차단용 테스트 포트만 사용한다.

## 상태 구분

| 구분 | 상태 |
|---|---|
| software complete | **PASS — 로컬 구현·단위 테스트·브라우저 검증 완료** |
| field configured | **BLOCKED / 미설정**. 실제 FIELD 좌표·구역·규칙·확인자 승인 없음 |
| deployed | **NOT DONE**. 로컬 코드만 변경 |
| robot validated | **NOT DONE**. 실제 주행 또는 경기 성공을 의미하지 않음 |

## 구현 범위

기존 주문 편집기·catalog/normalize_order 검증·방문 순서·Dijkstra를 재사용한다.
`SAVED_OCCUPANCY` 경로와 `SCHEMATIC_MANUAL`의 DEMO/FIELD 상태는 분리한다.
도식은 `MANUAL_GUIDANCE + MANUAL_STEP`이며 pose/ROS/SLAM 없이 표시·수동 기록만 한다.

- DEMO의 7개 장소는 예시다. FIELD에는 자동 복사하지 않는다.
- 현장 폼: A~D↔ZONE, 장소 접근 노드, 정지 x_px/y_px, yaw_rad, 규칙·지도 허용 확인,
  확인자와 별도 승인. 노드·edge·polyline·enabled·bidirectional은 상세 JSON 편집으로 제공한다.
- 서버가 중앙 차도 침범, 구간 내부의 미세한 단절, 불연결, 중복 ID/장소, 잘못된 역할,
  유한 좌표·yaw 범위·문서/요소 크기를 검사한다. UI만 맞추어 통과시킬 수 없다.
- 모든 세그먼트와 정차 순서는 서버 추천 결과가 원본이다. 브라우저에는 별도 경로 엔진이 없다.
- 픽업/배달은 도착 후 별도 기록. 최대 적재 5, 미수령 배달 금지. 구간 완료와 신호 판정은 별개다.
- 구간 이벤트는 route revision/progress revision/segment/event ID를 요구한다.
  동일 요청 재전송은 한 번만 반영하며, 이후 상태가 달라지면 409를 반환한다.
- 레이아웃 변경은 승인까지 해제한다. 컨텍스트/주문/출발점 변경은 추천·선택을 무효화한다.
  안내 중에는 먼저 표시 안내를 끝내야 한다. 재시작 후 자동 재개하지 않는다.
- 실제 위치 `LIVE_POSE_NOT_CONFIGURED`; 신호 UNKNOWN; 거리·ETA null.
  카드의 상대 비용은 미터나 초가 아니다. 운영자 마커는 센서 위치가 아니다.
- 기존 주문 객체의 20초 파생 필드는 호환 목적으로 유지하지만 도식 계산/화면에 사용하지 않는다.
  `legacy_order_timing_applicable=false`, `food_readiness_state=UNKNOWN`을 제공한다.
  확인된 사전준비 프로필은 음식별 2개 한도를 검사하며, 추가 준비 시간을 추정하지 않는다.

## 단계별 기록 (팩 01→07)

| 단계 | 변경/검사 | 결과와 다음 단계 |
|---|---|---|
| 01 감사 | AGENTS, HEAD, 기존 provider·gate·API·화면 구조 조사 | baseline Python 1438 (skip 1), JS 301 통과 → 별도 도식 뷰 |
| 02 뷰 | allowlist 로컬 자산, SVG 좌표계, 원본 탭·줌·팬·레이어 | 원본 변환 offset(30,88) 반영, 신호 8개 UNKNOWN → 모델 |
| 03 모델 | 별도 store/validator, FIELD 빈 입력, revision 승인 | 도로/불연결/범위/승인 차단 검사 → 공통 optimizer |
| 04 계획 | shortest_path/visit_orders 공유, 상대 비용 provider | 두 기존 모드 결과가 기준 HEAD와 전체 결과 단위로 일치 → 수동 기록 |
| 05 기록 | 구간·픽업·배달, concurrency/idempotency, restart fence | 네 출발지 왕복과 HTTP/ASGI no-motion 검사 → 공통 UI |
| 06 UI | 기존 panel/client, 설정 폼, 화면별 lifecycle | 실제 dashboard/Cockpit shell 및 작은 공통 패널 확인 → 최종 검사 |
| 07 인계 | 전체 회귀, 화면 캡처, 아래 실행/롤백 절차 | 최종 실행 결과는 다음 표 |

## 실행한 검사

명령은 저장소 루트에서 실행한다. 모든 브라우저 대상은 `127.0.0.1`이다.

| 검사 | 명령 | 최종 결과 |
|---|---|---|
| 전체 Python | `.venv/bin/python -m unittest discover -s tests -v` | **PASS: 1452개, skipped 1, 62.614초** |
| 전체 JS | `npm test` | **PASS: 306개** |
| 신규 실제 서버 E2E | `npx playwright test -c playwright.schematic.config.mjs --reporter=line` | **PASS: 4개, 19.5초** |
| 기존 Route Planner E2E | `npx playwright test --grep 'Route Planner\|route planner' --reporter=line` | **PASS: 8개, 22.2초** |
| diff 공백 검사 | `git diff --check` | PASS |

새 테스트는 실제 저장소 코드에 연결된다. 팩의 독립 route_core 예제를 테스트한 결과가 아니다.
현재 총계에는 보존한 다른 작업의 Python/JS/브라우저 테스트도 포함되어 있다.
신규 Python 검사는 ASGI를 직접 실행해 실제 router/model/coordinator를 검사한다.
브라우저 E2E는 실제 Python 서버에 HTTP 요청을 보낸다. httpx 테스트 의존성은 추가하지 않았다.
기존 mode golden은 기준 HEAD optimizer와 비교한 전체 route 결과 SHA-256이다.
`MANUAL_GUIDANCE`: `71fbe88719ac5c23f6a7c08f82ae29721a095a407c451b03301efa0a6ea1acd5`
`AUTO_NAV2`: `bbd46f10bceafa20608135218cd3f8ce5a5e6f2cf8549bdf8316e1d46cc87107`

초기 개발 중 신규 테스트의 overlay=null 기대값, HTTP 테스트 도구 의존성,
Cockpit 별도 창 대상 선택 문제를 발견·수정했다. 실패를 통과로 집계하지 않았다.
기존 다른 Cockpit 주행/waypoint 전체 E2E는 이번 검증 범위가 아니다.

## 수락 기준

| 항목 | 결과 / 근거 |
|---|---|
| 원본 출처 분리 | PASS: p11/p13 원본과 별도 도식; 생성 이미지 없음 |
| 4코너·4횡단보도·차도 금지·지하보도 OFF | PASS: template/geometry 검사, 화면 캡처 |
| 미확정 배치 | PASS: 초기 FIELD 빈 좌표/구역/승인; DEMO 배지 지속 표시 |
| 현장 편집·승인 | PASS: 브라우저 폼 입력→저장→별도 승인→수정 시 해제. 승인 테스트는 **TEST FIXTURE ONLY** |
| graph 검증 | PASS: finite/ID/역할/zone/segment 내부/불연결/미확인 지하보도 거부 |
| source 격리 | PASS: 기존 graph API가 도식 거부. map/annotation/known_free 검증 수정 없음 |
| planner 재사용 | PASS: shared shortest_path/visit_orders; 서버 추천만 사용 |
| 상대 비용·null | PASS: 도식 distance_m/eta_s null, ROS overlay null, 실제 위치 미연결 |
| pose 없는 수동 흐름 | PASS: 네 출발지의 구간·픽업·배달 완료와 왕복 |
| 중복/동시성 | PASS: expected revision, route/progress/segment pins, event ID와 coordinator lock |
| 신호 | PASS: 모든 구간 UNKNOWN, 완료 기록이 녹색을 만들지 않음 |
| 무주행 | PASS: 아래 trap/fetch 검사에서 실제 동작 포트 0회 |
| 서버 거부 | PASS: schematic preview/dry-run/export 거부, 기존 Mission router와 NavigationGoalRequest도 schematic payload 422 |
| 기존 보호 | PASS: same-origin/Competition Lock/mission·navigation·mapping gate 유지 |
| SavedMap 회귀 | PASS: 기존 Python/JS/Route Planner E2E 및 기준 HEAD 결과 비교 |
| source 전환 | PASS: 변경 시 STALE, 안내 중 전환 차단 |
| lifecycle | PASS: 공통 client 하나의 timer, 마지막 subscriber 해제, 반복 열기/닫기 |
| restart | PASS: 선택/추천 stale, 안내 비활성, 운영자 마커 제거 |
| offline UI | PASS: API unavailable일 때 읽기 전용 p11/도식 표시; CDN 불필요 |
| 접근성/반응형 | PASS: 라벨/키보드 표준 폼·스크롤·줌; 1366/1920/390px/DPR2 캡처 |
| 실제 pose 보정 | BLOCKED / 범위 밖: 등록값·실측값 없음, 자동 추적 OFF |
| 현장 배포 | NOT DONE / 사용자 금지 |

오프라인 검사는 ROS/API/외부 인터넷 없이 **로컬 정적 서버가 남아 있는 경우**다.
정적 서버까지 꺼진 뒤 신규 페이지를 열 수 있는 설치형 PWA/Service Worker는 추가하지 않았다.
FIELD의 모든 현장 위치를 승인했다는 의미가 아니다. 도식 yaw는 rad이며 실제 TF/yaw로 publish하지 않는다.

## no-motion 증거

신규 API는 GET/POST `/api/v1/route-planner/schematic` 두 개다.
POST action은 고정 enum이고 route/goal/ROS topic/임의 asset URL을 dispatch하지 않는다.
응답과 route의 `motion_authority=false`, `control_authority=false`를 검사한다.

테스트 harness는 Mission/Navigation/Control/agent/lifecycle/SavedMaps의 동작 포트를
`ActuationTrap`으로 둔다. 읽기 전용 activity gate 외 호출은 기록 후 즉시 실패한다.
실제 router를 통한 전체 수동 흐름 이후 trap 호출 목록은 빈 배열이다.
Mission 일반 생성 router는 실제 모델을 사용한다. Nav2 goal은 실제 요청 모델을 쓰는
테스트 endpoint에서 schematic 입력을 거부하며, 승인되면 반드시 trap을 호출하도록 되어 있다.
브라우저 요청 spy는 신규 변경 요청이 schematic endpoint에만 가는지 검사한다.
이것은 문자열 검색만 한 검증이 아니다.

실제 앱 전체 shell 캡처에서는 **planner만 실제 로컬 Python 상태**이고 나머지 telemetry는
기존 테스트 fixture다. 화면의 Bridge/Control 표시를 실제 Go2 연결·주행 상태로 해석하지 않는다.
기존 회귀 E2E의 Mission draft/export 역시 로컬 mock에서만 실행되며 실제 Mission은 없다.

## 캡처와 로그

최종 결과 사본은 이 작업 공간의 `outputs/`에 있다.
`schematic-1366x768.png`, `schematic-1920x1080.png`, `schematic-cockpit-narrow.png`,
`schematic-field-unconfigured.png`, `schematic-offline-dpr2.png`,
`schematic-dashboard-shell.png`, `schematic-cockpit-shell.png`.
마지막 두 장은 실제 shell + 로컬 planner + 다른 telemetry fixture 조합이다.
전체 테스트 로그 4개와 이 인계 문서 사본도 함께 제공한다.

## 변경 파일과 보존한 변경

신규: `route_planner/schematic.py`, `schematic_session.py`, `api/routers/schematic.py`,
`static/features/route_planner/{competition_map_view.js,schematic_controls.js,schematic.css}`,
`scripts/install_schematic_assets.py`, 신규 Python/JS/E2E 테스트·로컬 harness·전용 Playwright config,
감사/인계 문서.

확장: `route_catalogs.py`, `route_planner_coordinator.py`, `optimizer.py`, `state_store.py`,
공통 `route_planner_client.js`, `route_planner_panel.js`, CSS import,
API inventory 검사, 기존 Playwright config의 전용 suite 분리, `.gitignore`.
`app.py`(1597줄), `app.js`(6898줄), 기존 graph.py/annotation/occupancy 검증은 바꾸지 않았다.

작업 도중 별도로 추가된 `mission_panel.js`, `test_mission_coordinator.py`,
`reusable_points_orders.spec.mjs`, `test_order_sheet_roundtrip.mjs`와 공통 panel/CSS의
주문 행 배치 변경은 사용자/다른 작업 소유로 보존했다. 이 작업 성과로 주장하지 않는다.
공유 파일을 통째로 되돌리면 이 변경들도 사라지므로 금지한다.

## 자산과 저장

원본 공개·재배포 권한은 확인되지 않았다. `static/assets/competition/gangnam2026/`는
gitignore에 포함하며 공개하지 않는다. 설치기는 고정 5개 파일/해시를 확인하고
script/foreignObject/외부 URL/동적 SVG를 거부한다. 원본 SVG는 유지하고 신호만 분리한
`arena_background.svg`를 로컬에서 생성한다. 템플릿도 로컬 팩에서 설치한다.

저장은 기존 private atomic store를 별도 `route-planner/schematic/route-planner.json`에 재사용한다.
0700 디렉터리/0600 파일, 크기 제한, symlink 거부, 임시 파일→fsync→replace.
schema v1은 기존 SavedMap 상태를 변환하지 않는 신규 provider다.
알 수 없는 schema는 추정 migration 없이 unavailable 처리한다.

## 로컬 실행

저장소 루트:
`/Users/hajoonpark/Documents/Codex/2026-08-07/new-chat/work/github-publish.p5EymP/repo`

```sh
.venv/bin/python scripts/install_schematic_assets.py /Users/hajoonpark/Documents/자율설계/gangnam_manual_guidance_pack
.venv/bin/python -m uvicorn schematic_offline_server:app --app-dir tests --host 127.0.0.1 --port 4188
```

`http://127.0.0.1:4188/`의 로컬 테스트 화면에서 DEMO 선택 → 아래 기존 주문서 저장·잠금 →
출발 장소 선택 → 추천 → 선택 → 수동 안내 시작 → 구간/픽업/배달 기록 순서다.
이 서버는 매 실행 임시 저장소를 사용하며, 실제 ROS 앱/robot 서비스를 시작하지 않는다.
전체 shell `/dashboard`는 E2E mock 없이 실제 telemetry를 제공하지 않는다.
현장 웹 주소 `192.168.50.10:8088`에는 이번 변경이 배포되지 않았다.

전용 E2E는 `playwright.schematic.config.mjs`로 실행한다. 기본 E2E 서버와 혼용하지 않는다.
`SCHEMATIC_OUTPUT_DIR`를 지정하면 캡처가 그 디렉터리에 생성된다.
전체 Python 검사는 공개 가능한 합성 테스트 템플릿을 사용하므로 로컬 팩 설치가 필요 없다.
원본 자료를 표시하는 전용 브라우저 E2E와 로컬 DEMO 실행에는 위 설치가 선행되어야 한다.

## 현장에서 남은 입력 / 다음 한 단계

다음 단계는 배포가 아니라 **로컬 DEMO 화면 확인**이다. 실제 FIELD 사용 전에 별도로:

1. 경기장 방향과 코너 A~D↔공식 ZONE1~4를 확인한다.
2. 4배송지·3식당 각각 접근점 1개와 필요 시 두 번째 접근점, 정지점, 방향(yaw_rad)을 입력한다. 두 접근점은 하나의 정지점으로 연결되며 미확인 값은 비워 둔다.
3. 도식 내 연결/폐쇄/단방향을 확인한다. 지하보도는 실제 연결 확인과 edge 활성화를 따로 한다.
4. 조종 경기 사전준비 규칙 및 정적 지도 사용 허용을 확인한다.
5. 확인자가 이름을 직접 입력하고 해당 layout revision을 별도로 승인한다.

실측 지도와의 보정·실제 pose 자동 추적·신호 인식·주행 명령은 이번 기능에 없다.
최대 5개를 넘는 주문 또는 확인된 프로필의 음식별 2개 초과는 분할/별도 준비 절차가 필요하다.

## 롤백

현재 외부 배포는 없으므로 현장 롤백 작업은 없다. 로컬 테스트 서버는 실행 터미널에서 종료한다.
변경 취소가 필요하면 이 작업의 diff만 선택적으로 되돌린다. `git reset --hard`, 파일 전체 checkout,
공용 상태/사용자 지도 삭제는 하지 않는다. 로컬 참고 자산·임시 상태는 공개하지 않는다.
이전 승인/진행 기록은 자동 복원하거나 새로운 현장 배치의 승인으로 재사용하지 않는다.

## 2026-09-12 공개·배포 승인 후 추가 점검

사용자가 커밋·푸시와 외부 Jetson 대시보드 배포·재시작을 별도로 승인했다.
위 상태 표와 초기 로그는 최초 로컬 인계 당시 기록이며 배포 성공을 주장하지 않는다.
실제 배포 결과·정확한 release ID·복구 경로는 별도 운영 기록에 남긴다.

- 이번 기능만 분리한 임시 검증 복사본에서 Python **1452개 (skip 1)**, JS **306개**,
  기존 Route Planner 및 자산 미설치 브라우저 회귀 **8개** 통과.
- Python 검사는 합성 템플릿으로 실행한다. 비공개 지도/이미지는 Git에 넣지 않는다.
  합성 좌표는 테스트 전용이며 운영 코드나 FIELD 초기값으로 사용하지 않는다.
- 참고 자료가 없을 때 도식은 unavailable로 차단하되 기존 저장 지도 주문 편집기는 유지한다.
- 내부망 HTTP에서는 `randomUUID()` 대신 `getRandomValues()`로 수동 기록 ID를 생성한다.
- 기존 현장 수정 네 파일(주문 행 CSS, 미션 반복 방문 UI, 주문 행 패널, 주문 객체 투영)은
  이번 공개 커밋에서 제외하고 별도 배포 보존 patch로 관리한다. 새 디자인 작업도 제외한다.
- 검증 복사본에는 독립 Git 메타데이터를 사용한다. 공유 Git 환경변수를 주입한 초기 시도는
  테스트 fixture가 원본 로컬 설정에 영향을 주어 폐기했다. 테스트용 미공개 커밋을 복구하고,
  원본 HEAD·main·작성자 설정·작업 파일 보존을 재확인했다. 원격에는 전송하지 않았다.
- 기존 인터페이스 검사에서 2초 제한 초과가 한 번 발생했으며, 제한 변경 없이 전체 재실행이
  50.843초에 통과했다. 실패 시도를 최종 통과로 숨겨 집계하지 않는다.
