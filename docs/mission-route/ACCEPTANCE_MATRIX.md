# MR 요구사항 인수 매트릭스

기록 UTC: 2026-10-15T06:45:34.358571+00:00. **전체 PARTIAL**. pack90의45개 행을 추적한다. S software / I MR-MS 통합 / N actual native / H 실기 / F 후속이다. PASS는 관측 열의 fixture/software 범위다. actual code와 synthetic hardware provider를 구분하며 live/runtime까지 확대하지 않는다. N/H/F 미지원·미수행은 명시 유지한다.

source `22c7913c879afcca536a78d552dcdf98f0f53098`, manifest의 commit source_dirty=false. 로컬 검사는 당시 uncommitted/dirty tree였고, 그 bytes를 동일하게 커밋한 source SHA로 사후 대응했다. 개별 실행 당시 checkout HEAD는 별도로 기록하지 않았으며 이를 clean commit 실행으로 주장하지 않는다. runtime_sha/config_hash=null. command·시각·로그 원본/SHA256·환경은 [VALIDATION.json](VALIDATION.json), source30개 hashes는 [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json)이다. focused83, Python1939(skip2/fail0), Node381, Ruff/configured mypy4/syntax/diff/secrets, Chromium96 PASS. 로그에는 장비 증거가 없다.

manual_action_performed=false. 배포/restart/initialpose/ARM/motion goal/실이동 없음. final_resource_state=운영 서비스·camera·SLAM 미변경, fixture servers/runner 종료. actual native·실기는 NOT_RUN이다. source/run source_sha·runtime_sha를 혼동하지 않는다; persisted run은 둘 다 null이다.

| ID | 범위 | 단계 | 상태 | 합격 기준 | 관측·남은 조건 |
|---|---|---|---|---|---|
| MR-01 | S | 21 | PASS | 전용 지도 중심 편집/검사/실행과 Cockpit 요약이 같은 run을 사용 | 앱 singleton/coordinator wiring·Cockpit/client 회귀 및 Chromium96 PASS. 서로 다른 실행 owner 없음. |
| MR-02 | S | 21 | PASS | 지도·방문 목록 선택/순서/추가/삭제/undo가 양방향 일치 | Node state reorder/duplicate/undo, browser 지도·목록·키보드/drag fixture PASS. |
| MR-03 | S | 21~24 | PASS | 동일 POI 반복 방문의 visit_id·작업·순서를 보존 | 실제 coordinator/service repeated POI·heading fixture PASS, visit ID 보존. |
| MR-04 | S | 21,23 | PASS | 현재 운영 위치·가상 시작점·HOME·복귀를 구분, 편집 중 명령 없음 | 운영 pose/가상 preview start/HOME annotation 분리. HOME 복귀는 명시 방문. service 무동작·browser HOME fixture PASS. |
| MR-05 | S | 22,25 | PASS | heading/대기/전후 확인이 요청→저장→조회→실행 의미까지 일치 | HTTP/저장/compile→실제 coordinator heading dispatch·최종 hold/전후 token fixture PASS; browser 상세 저장 PASS. |
| MR-06 | S | 22 | PASS | 지원 안 되는 speed/tolerance/action을 effective 또는 완료로 표시하지 않음 | 서버 custom action/speed/tolerance/pass-through 거부 PASS. UI unavailable 이유 표시. |
| MR-07 | S | 22,25 | PASS | 마지막 visit의 대기·확인·작업까지 끝난 뒤 mission completion | final monotonic hold와 after confirmation 뒤만 completed, skip은 completed_with_skips fixture PASS. |
| MR-08 | S | 21,22 | PASS | draft polling/CAS conflict/reload가 unsaved 변경을 조용히 지우지 않음 | Node delayed save/reload/CAS·browser focused input/polling/late response·다른 지도 이력 복귀 PASS. |
| MR-09 | S | 24 | PASS | E1 geometry와 의미 있는 방문/작업을 별도 보존, hidden truncation 없음 | E1 원본 geometry/revision·STOP 후보 분리, browser E1→저장→compile PASS. selector 최대32 후보 안내. |
| MR-10 | S | 20~26 | PASS | legacy annotation mission·지도·주문·도식·layout/테마를 보존 | 전체 Python/JS/Chromium의 legacy mission/maps/orders/spatial/SLAM 및 dark/light 회귀 PASS. |
| MR-11 | S | 22,24 | PASS | 새 자유좌표 미션이 기존 지도 annotation을 몰래 생성/변경하지 않음 | mission_local_pose와 annotation_ref 분리, compile/run 무동작·annotation override 원본 불변 fixture PASS. |
| MR-12 | S | 23,24 | PASS | map/family/annotation/route/context pin을 서버에서 현재 값과 검사 | server exact family/revision/context/process generation 및 paused stale annotation 거부 fixture PASS. |
| MR-13 | S | 23,24 | BLOCKED | 시작 connector·모든 leg·simplified geometry/결과 path까지 footprint 검사 | software endpoint/connector/path 검사 PASS. 실제 effective footprint provider 연결 없어 인수 BLOCKED. |
| MR-14 | S,N | 23,27 | BLOCKED | occupied/unknown goal뿐 아니라 unknown 경로 통과·KEEP_OUT 침범 거부 | software unknown connector/KEEP_OUT validator 회귀 PASS. runtime unknown/KEEP_OUT proof 미연결, native NOT_RUN. |
| MR-15 | S | 23 | PASS | rotated origin/단위/방향 변환 정확, native map 미지원은 명시 차단 | JS rotated transform roundtrip·기존 spatial/map 회귀 PASS. native sparse map을 occupancy로 만들지 않고 readiness로 차단. |
| MR-16 | S | 21,23 | PASS | 작성선·fixture·실제 Nav2 계획·관측 궤적이 명확히 구분됨 | browser 작성/E1/fixture/native 라벨·dispatch plan/trajectory 분리 PASS. live_plan unavailable 유지. |
| MR-17 | S | 23 | PASS | native adapter가 실제 action 호출·timeout/cancel/응답 검증을 구현 | 실제 Humble action adapter + synthetic transport4 PASS; 실제 server는 MR-18. |
| MR-18 | N | 27B | NOT_RUN | 실제 설치 Nav2 planner의 계획·거부·frame·config를 확인 | 실제 ROS/native resource 창 없음. 설치된 server/plugin/config 호출 NOT_RUN. |
| MR-19 | S,N | 23,24,27B | NOT_RUN | preview/validate/compile이 goal/ARM/initialpose/control 명령을 만들지 않음 | S: 실제 service/planner code 무 motion fixture PASS. N: 실제 ROS graph 부작용 관측 NOT_RUN. |
| MR-20 | S | 23 | PASS | 오래된 preview 응답·지도/설정 변경이 새 draft에 적용되지 않음 | Node generation·late preview, service wrong generation·map/context gate·browser stale draft PASS. |
| MR-21 | S | 24 | PASS | FLEXIBLE compiler가 작업/방문 순서를 보존해 기존 coordinator에 연결 | service immutable compile·기존 coordinator run 연결 및 E1 UI compile fixture PASS. production start는 policy BLOCKED. |
| MR-22 | S | 24,28 | PASS | unsupported CORRIDOR/STRICT/무정차를 서버가 거부, 작성과 실행 구분 | schema/capability gates에서 unsupported modes/arrival/action 거부 PASS. 실행 가능 표시 없음. |
| MR-23 | S | 23~25 | BLOCKED | 실제 실행 시 새 계획 가능성 표시, 최신 계획 정책 적용 경로 검증 | 각 leg fresh pose preflight 및 재계획 안내 PASS. runtime policy provider·live path provenance 없어 BLOCKED. |
| MR-24 | S | 22~25 | PASS | 중복 create/compile/start/confirm/retry가 이중 run·goal·작업을 만들지 않음 | CAS/idempotency/token/receipt bounded run_ref·중복 start/admission fixture PASS. 외부 action exactly-once는 미지원. |
| MR-25 | S | 25 | PASS | 잘못된 goal ID/세대·늦은 terminal은 현재 방문 완료에 영향 없음 | 다른 goal terminal·uncertain send·source/process generation 변경 actual code fixture PASS. |
| MR-26 | S | 25 | PASS | cancel timeout/uncertain/ownership loss에서 새 goal 차단·원인 보존 | cancel timeout/foreign goal/불확실 제출에서 owner 유지·새 goal 차단, audit failure cleanup fixture PASS. |
| MR-27 | S | 22,25 | PASS | pause 대기 잔여시간·wall clock 변경·restart를 정의한 대로 처리 | monotonic/paused hold 잔여/paused restart interrupted fixture PASS. |
| MR-28 | S | 25 | PASS | 재시작/페이지 복원/연결 회복이 자동 ARM/resume/goal 재전송 안 함 | running/paused restart interrupted·reload/연결 회복 무재전송 synthetic regression PASS. |
| MR-29 | S | 22,25 | PASS | 정의와 run 이력 분리, skipped/failed/uncertain 작업을 정상 완료로 숨기지 않음 | immutable definition/run·active copy·skip outcome·delete history·token-free export PASS. |
| MR-30 | S | 22,26 | PASS | API strict/same-origin·private storage·path/token·oversize 방어 | strict/origin/id/path/NaN·symlink/corrupt/oversize/private storage fixtures·secret scan/API inventory PASS. |
| MR-31 | S | 20,26 | PASS | MR 전용 모듈·CSS로 MS 영역과 분리, 공유 hook은 수락 후 적용 | MR scoped source/CSS·MS 단독 shared hook 창 확인, 전체 theme/SLAM browser regression PASS. |
| MR-32 | S | 20~26 | PASS | MS 미연결이어도 실제 legacy read port로 작성 가능, VSLAM live를 가짜로 채우지 않음 | actual legacy port authoring·실제 MS projection source null 유지 fixture PASS. VSLAM engine 승격 없음. |
| MR-33 | I | 26 | PASS | MR active/paused/canceling 동안 MS source/map 변경 및 삭제 충돌을 양방향 차단 | actual MR/MS manager/configure 교차8에서 running/paused/canceling↔MS mutation gate PASS. synthetic hardware providers; live NOT_RUN. |
| MR-34 | I | 26 | PASS | MS mapping/save/localize와 MR start 충돌을 양방향 차단 | 동일 actual code 교차에서 MS busy→MR/legacy start, MR active→MS mutation 거부 PASS. live NOT_RUN. |
| MR-35 | I | 26 | PASS | navigation content/context 변경과 preview/name/sequence 갱신을 구분 | actual projection pose sequence 안정/운영 source generation pin·legacy process generation 독립 pin fixture PASS. |
| MR-36 | S,I | 20~26 | PASS | 동일 checkout 쓰기/전체 suite/Git index 동시 사용 없음, 타 변경 보존 | 상호 조율·창 반환 후 source 적용/전체 test/Git 순차 진행. MS docs·전용 source·사용자 data 보존. |
| MR-37 | S,I | 26 | PASS | 단일 후보의 Python·JS·정적·E2E·CI 결과와 skip/환경 실패를 구분 | 단일 source bytes/manifest에 Python1939·JS381·quality·Chromium96 PASS. exact b42b28f CI38694446361 두 Linux 환경 success(Python1939/skip1, JS381, Chromium96). CI.json 참조. |
| MR-38 | S | 21,26 | NOT_RUN | 1024/1280/1440/portrait·200% zoom·키보드/touch에서 핵심 조작 접근 가능 | responsive/keyboard/CSS200% fixture PASS·캡처 검토. 실제 browser zoom200%·touch hardware NOT_RUN. |
| MR-39 | S | 21,25 | PASS | software STOP·HUD·manual takeover가 overlay/drawer에 가려지거나 재정의되지 않음 | 기존 STOP/HUD/수동전환 adapter·pointer 접근·responsive 브라우저 회귀 PASS. 물리 stop은 MR-42. |
| MR-40 | H | 27A | NOT_RUN | exact 배포 후보·기존 데이터·MS 상태·rollback·최종 ownership 확인 | 단계27 장비 창 없음, source/data/service rollback 실제 미수행. |
| MR-41 | H | 27C | NOT_RUN | 통제 구역에서 짧은 미션 도달·정지·중간/마지막 작업 확인 | 도달·물리 정지·중간/마지막 작업 실장비 관측 없음. |
| MR-42 | H | 27C | NOT_RUN | pause/resume/abort·수동 전환·실제 stop 관측을 별도 기록 | pause/abort/takeover software fixture만 PASS. 실장비 stop 관측 없음. |
| MR-43 | F | 28 | BLOCKED | CORRIDOR 제한이 계획·재계획·추종 전 과정에 적용 | 후속 범위. CORRIDOR runtime 제약 미지원, 현재 실행 거부. |
| MR-44 | F | 28 | BLOCKED | STRICT supported controller와 deviation/obstacle stop 확인 | 후속 범위. STRICT controller/deviation/obstacle stop 미지원, 현재 실행 거부. |
| MR-45 | F | 28 | BLOCKED | 무정차 경유 또는 teach-repeat를 cmd_vel replay/가짜 완료 없이 구현 | 후속 범위. 무정차/teach-repeat 미지원; cmd_vel replay/가짜 완료 없음. |

MR-13/14/23은 effective runtime provider 미연결이라는 software blocker다. MR-19의 software 무동작 PASS와 실제 graph 미수행을 분리했다. MR-38의 CSS zoom fixture를 actual native browser zoom/touch 합격으로 올리지 않았다. F행은 기본 단계20~26 이후 범위이며 현재 서버가 거부한다. MR-37은 원격 exact b42b28f CI success로 갱신했다. 후속 문서 commit이 이 run에 포함됐다고 주장하지 않는다.
