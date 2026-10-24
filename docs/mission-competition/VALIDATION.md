# 대회 미션 패널 검증 — 2026-10-24

최종 통합 기준은 `main@1cddada91585c63637d74e0560e89009f2f2a11a`이다. 새 미션 변경만 추가하며 해당 main의 VM 모델·traffic·avoidance·integration 산출물과 관측 화면 변경을 보존했다. 다른 사용자 체크아웃의 미커밋 변경은 수정하지 않았다.

## 결과

| 검사 | 최종 결과 |
| --- | --- |
| 전체 Python unittest discover | 2,691개 실행: 2,689 PASS, 2 SKIP, 실패 0 |
| 전체 JavaScript 단위 검사 | 660 PASS, 실패 0 |
| 기존 관련 Playwright 회귀 | 90 PASS |
| 신규 대회 real-API fixture Playwright | 4 PASS |
| 변경 Python 파일 Ruff / git diff --check | PASS |
| JSON Schema와 현재 모델 비교 / 고정 DRAFT fixture 검증 | PASS |
| 1440×900·390×844, dark/light 화면 | 저장된 4개 스크린샷 확인 |

건너뛴 Python 검사 2개는 기존 선택 기능이다.

- `test_overlay_artifacts_label_synthetic_and_not_operational`: optional SVG plotting dependency absent.
- `test_real_humble_cdr_serialization_is_decoded_offline`: optional rosbags backend not installed.

전체 Python/Node 및 브라우저 검사는 sandbox의 asyncio 종료·test-runner 제약을 피한 로컬 테스트 환경에서 실행했다. 테스트용 서버만 loopback에 띄웠으며 production app은 import/기동하지 않았다. 처음의 fixture 포트 4174 충돌은 테스트 설정을 별도 4187로 변경해 해결했다. 충돌한 프로세스를 종료하거나 재사용하지 않았다.

최신 main 통합 후 발견한 app.py 크기 제한은 기존 wiring 모듈에 종료 hook을 두어 해결했다. Cockpit으로 돌아가는 기존 검사도 별도 창을 여는 sidebar 대신 같은 탭의 기존 route를 사용하도록 고쳤다. 검사 제한·assertion을 완화하지 않았다.

## 검사 범위와 증거

- 기존 정의의 직렬화 shape/digest 보존, 새 step/visit ID, 저장·재조회·실제 Python fixture adapter dispatch 필드 일치, 최소 2초/5초·유한 숫자·legacy/운영자 우회 혼합 거부.
- RED/UNKNOWN, 앞발 한 개, PROXY, 잘못된 signal/crossing, 미완료 dwell, stale image, missing pose, path 차단. 정상 GREEN과 유효 조건에서는 새 exit generation을 보내고 실제로 완료된다.
- 접근 terminal/cancel ACK 뒤 HOLD, HOLD ACK 뒤 물리 조건 누적. 의도된 HOLD_SIGNAL과 WAIT_OBSTACLE 및 NAVIGATION_PROGRESS_FAILED 분리.
- 이전 goal/owner/producer epoch/sequence/config 결과, evidence gap, 중복 start/cancel, active 정의 수정 거부, 불변 run pins, 저장 실패 후 잘못된 RUNNING/완료 표시 방지.
- browser close/reconnect 동안 서버 timer·단계 유지, 새 탭에서 같은 시도 조회, backend restart에서 INTERRUPTED 및 green/dwell/goal 비복원.
- native 미연결별 blocker, fixture/native path 증거 구분, 카메라 원본·processed handle 미연결 표시, GLB checksum/geometry decode·정합 미확인, 지도 semantic revision과 heartbeat 분리.
- 기존 LiDAR/카메라 transport·VSLAM/SLAM·지도 편집·manual STOP/E-stop·서비스 blocker·미션 저장 및 실행·테마·모바일 회귀.

신규 E2E는 `tests/competition_fixture_server.py`에서 실제 FastAPI mission router, PlanStore, service, executor를 실행한다. 다른 대시보드 provider와 지도·센서는 명시적인 fixture다. navigation adapter의 send_goal/cancel_goal은 호출되면 AssertionError를 낸다. 가짜 성공 응답만으로 backend 동작을 검증하지 않았다.

스크린샷은 `competition-{1440,390}-{dark,light}-explicit-fixture.png`이며 별도 결과물로 제공한다. 화면 안에 합성 fixture임을 표시했다. Go2/ROS 관련 다른 대시보드 표시는 테스트 backend가 제공한 합성 UI 데이터이며 장비 연결 증거가 아니다.

## 재현 명령

프로젝트의 Python/Node 테스트 의존성과 Playwright Chromium이 있는 환경에서 실행한다.

```sh
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
npx playwright test tests/e2e/mission_route.spec.mjs tests/e2e/mission_page.spec.mjs tests/e2e/dashboard.spec.mjs tests/e2e/spatial_editor.spec.mjs tests/e2e/reusable_points_orders.spec.mjs tests/e2e/slam.spec.mjs
npx playwright test --config playwright.competition.config.mjs
```

fixture 서버 기본 주소는 `127.0.0.1:4187`이다. 필요하면 `COMPETITION_FIXTURE_PORT`로 별도 로컬 포트를 지정한다. 기존 서버 자동 재사용은 금지되어 있다. source diff와 로그 요약은 이 결과의 첨부물이며 실행 이력을 native resume 데이터로 사용하지 않는다.

## 실행 가능한 범위

저장·편집·정의 검사·GLB 설계 뷰·명시적 backend fixture 시도·이력 export가 가능하다. 기존 일반 미션의 실행 gate는 유지했다. 새 대회 행동의 native execution은 모두 UNCONNECTED이며 fixture PASS로 활성화되지 않는다.

VM의 합성 검증 보고를 읽기 전용 adapter로 연결했지만 이번 테스트가 VM 알고리즘이나 로봇 적합성을 재검증한 것은 아니다. 실제 YOLO 모델/실영상, 앞발 실측, 물리 정지·gait/posture, 단일 arbiter ACK/TTL/epoch, 실제 Nav2 path, map–arena 정합과 Jetson 검증은 다음 통합 대상이다. 상세 contract 차이는 HANDOFF.md에 있다.

실장비 배포·서비스 재시작·카메라 인수·ARM·initialpose·실제 goal·이동·장비 저장소 migration은 수행하지 않았다.
