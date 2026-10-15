# MR 진행 기록

갱신 UTC: 2026-10-15T06:45:34.358571+00:00. 작업: MR — 경로·미션. **전체 인수 상태 PARTIAL**: 단계20~26 제품 코드와 소프트웨어 통합 검증은 완료했지만 effective runtime 정책 제공자 연결(MR-MS-003)이 빠져 있다. 장비 배포 완료를 뜻하지 않는다.

| 항목 | 확인 상태 |
|---|---|
| 기준 origin/main | `7747ef7dd536a8aa0f313784374e00693e8696c3` — MS 문서 포함, MR 적용 전 |
| MR source commit | `22c7913c879afcca536a78d552dcdf98f0f53098` — 기존 main, source/tests 30개 |
| 현재 변경 | MR 문서·synthetic 캡처만 정리 중. MS 전용 dirty/staged 없음 |
| 쓰기·전체 테스트·Git 담당 | MR 단일 창. MS 완료/read-only, writer·fixture server 종료 |
| 실제 runtime SHA/config hash | null / 미확인. 장비에 접속하지 않음 |
| 게시/CI | MR 발행 전; 아래 게시 기록은 실제 결과 뒤 갱신 |
| 배포/native/실기 | NOT_RUN, 단계27 창 없음 |

## 단계20~26 결과

| 단계 | 적용 결과 |
|---|---|
| 20 | 최신 AGENTS, main/origin, dirty/staged, 기존 MissionCoordinator/E1 및 MS HANDOFF 조사. 공유 쓰기 창 상호 인계 |
| 21 | 지도 중심 편집/검사/실행 workspace, 목록·inspector·구간 상세, 키보드/드래그/undo, 기존 singleton client·Cockpit 요약 |
| 22 | stable visit ID, heading/hold/전후 확인, strict/CAS 저장·복사·삭제, immutable run, same-origin API |
| 23 | 실제 Humble ComputePathToPose adapter, 지도/세대 pin, endpoint·connector·결과 path 검사, 실제/fixture 구분 |
| 24 | E1 원본 geometry/revision 보존, 검토할 STOP 초안, FLEXIBLE compile·별도 run 생성, 기존 coordinator 연결 |
| 25 | 마지막 hold/확인 실행, pause 잔여시간, 자기 goal ownership·취소 불확실성, interrupted 복원, bounded 이력·비교/export |
| 26 | MR+legacy/MS 실제 코드 교차8, 앱 wiring/API inventory, Python·JS·정적·전체 Chromium 회귀 및 캡처 검토 |

지도 선택 → 방문 편집 → 저장 → 작성 검사 → native preview(자원 창 필요) → FLEXIBLE compile → run 생성 → 별도 start 흐름이다. 작성·저장·compile·run 생성은 이동 명령을 보내지 않는다. 새 실행은 현재 production runtime proof 부족으로 차단된다.

## 변경 파일과 검증 후보

정확한 30개 source/test 경로·SHA256은 [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json)에 있다. MR domain7/router1/coordinator1/UI4/Cockpit3, 합의된 공유 app/runtime2, Python tests6/Node1/E2E5다. 공유 source/tests4개는 MS가 단독 통합 창에서 적용하고 MR coherent commit 포함을 확인했다. MS 문서5개는 MS commit에 이미 들어 있어 MR commit에서 제외했다.

검증은 커밋 전 동일한 source bytes에 대해 실행했으며 이후 source 변경 없이 `22c7913c879afcca536a78d552dcdf98f0f53098`로 커밋했다. docs/evidence만 후속 변경한다. 기록·명령·시각·원본 log hash·환경은 [VALIDATION.json](VALIDATION.json)을 따른다.

| 검사 | 결과 |
|---|---|
| focused Python | 83/83 PASS, 2.557초, skip0. 실제 MR/MS 교차8·실제 NativePlanner + synthetic transport4 포함 |
| 전체 Python | 1,939 발견, 1,937 PASS / skip2 / fail0, 81.974초 |
| Node 전체 | 381 PASS / skip0 / fail0 |
| Ruff | robot_dashboard/scripts + 새 Python tests PASS |
| configured mypy | 설정 대상4 modules PASS; 프로젝트 전체 typing 완료라는 뜻 아님 |
| frontend syntax / diff / secrets | PASS |
| 전체 Chromium | 96 PASS / skip0 / fail0 / flaky0, 151.110초. local synthetic HTTP fixture |
| 화면 검토 | dark/light, 1440/1280/1024 landscape, 768 portrait, 390 mobile, 200% CSS zoom fixture |

Python skip: optional rosbags 미설치, macOS에서 Linux process sessions와 /proc 전용 검사 불가. 200%는 CSS zoom fixture이며 실제 browser zoom·touch hardware는 NOT_RUN이다. 전체 browser 결과에는 legacy/cockpit/orders/spatial/maps/SLAM 회귀가 포함된다. 화면 캡처는 [evidence](evidence/)이며 모두 `UI fixture / 주행 검증 아님` 표시다.

## 공유 요청과 남은 조건

- MR-MS-001/002: **VERIFIED (software)**. router/runtime·default false CLI 적용, actual code 교차·앱 wiring·전체 회귀 PASS. native/live 검증은 별도 NOT_RUN.
- MR-MS-003: **PROPOSED/BLOCKED**. app은 policy_provider를 주입하지 않고 기본 {}를 쓴다. effective planner/footprint·runtime unknown/KEEP_OUT 증거 read port의 쓰기 소유권 수락과 구현이 필요하다. fixture true로 대체하지 않았다.
- MR-MS-004: 추가 공유 수정은 **PROPOSED**. MR consumer의 운영 pose/odometry source 분리·process generation pin은 구현/교차 fixture PASS다.

`live_plan`은 provenance 부족으로 unavailable이다. dispatch 전 계획을 최신 controller path로 부르지 않는다. run source/runtime SHA도 null이다. run32/receipt256 등 상한 뒤 maintenance/archive API는 없다. unsupported action/speed/tolerance/PASS_THROUGH/CORRIDOR/STRICT/zone 실행은 거부한다.

다음 최소 작업은 MR exact tip 게시·CI 기록, MR-MS-003 read-only provider 계약 수락/연결이다. 27단계 별도 조건 전 배포·서비스 재시작·initialpose·ARM·motion goal·실이동은 하지 않는다. 이미 통과한 검사를 변경 없이 반복하지 않는다.
