# Validation · 2026-10-07

저장소 `Phjrab/robot-scope-ros2-dashboard`, 시작 HEAD `92194cad2f2f91add260791f2e73f86db6bcbd20`. 모든 명령은 저장소 루트에서 실행했다. 소스 변경은 정적 프런트엔드와 테스트/문서에 한정했다.

## 실행 결과

| 상태 | 명령 | 결과 · exit code | 증거 |
|---|---|---|---|
| PASS | `npm run test:unit` | 340/340 · 0 | evidence/after-js-unit.txt |
| PASS | `npm run test:cockpit` | 107/107 · 0 | evidence/after-cockpit-unit.txt |
| PASS | `npm run test:cockpit:e2e -- --reporter=line` | 21/21 · 0 | evidence/after-cockpit-e2e.txt |
| PASS | `npm run test:e2e -- --reporter=line` | 기존 67/67 (Cockpit 21 포함) · 0 | evidence/after-all-e2e.txt |
| PASS | `npx playwright test -c playwright.ui-redesign.config.mjs --reporter=line` | 신규 8/8 · 0 | evidence/after-ui-e2e.txt |
| PASS | `.venv/bin/python -m unittest discover -s tests -p 'test_final_architecture.py' -v` | 5/5 · 0 | evidence/after-architecture.txt |
| FAIL · 기존 오류 | `.venv/bin/python -m unittest discover -s tests -v` | 1483 tests; 1481 pass, error 1, skip 1 · 1 | evidence/after-python.txt |

Python 남은 오류는 `OfflineRegistrationTests.test_extended_matrix_records_failures_separately_from_acceptance`다. extended registration benchmark subprocess가 exit 1로 종료한다. baseline도 같은 테스트 오류를 기록했다. 해당 Python/C++ 코드는 변경하지 않았다. baseline 환경의 fastapi/pydantic import 오류 5개는 기존 requirements를 로컬 .venv에 설치한 뒤 해소했다. 새 제품 dependency/lockfile 변경은 없다. skip은 PASS에 포함하지 않는다.

구현 중 발견한 패널/toolbar 겹침, 고급 상태 버튼 clipping, Settings 진단 다운로드 HUD 가림을 수정했다. 중간 실행 기록은 `evidence/iterations/`에 모았다. 최종 전체 67개·신규 8개 실행에는 이 회귀가 없다.

기존 baseline Cockpit E2E는 20 PASS / 1 FAIL(겹친 Mission 패널이 Navigation STOP을 가림)이었다. 최종 테스트는 실제 launcher focus와 작업영역 경계를 사용하며 ARM/소유권/STOP/구독 assertions를 유지한다. Navigation을 mock 시작하기 전에 Apply하고, 서버 소유권으로 Operate가 강제되는 계약을 따르게 순서를 수정했다. 전체 Python 실패를 UI 성공으로 숨기지 않는다.

## UI·접근성 실제 검사

- Chromium: 1440×900, 1366×768, 1024×768, 390×844. 720×450은 1440×900의 200%에 해당하는 CSS 가용 viewport 검사이며 브라우저 chrome 확대나 접근성 인증은 아니다.
- 기본 Cockpit scene은 desktop/tablet workspace 폭의 약 67~75%; 최소 scene 높이 >200px. 모바일에서는 inspector를 접고 가로 tool rail을 스크롤한다. 고급 메뉴는 접힌 popover로 접근한다.
- keyboard Enter로 Safety 상세 열기, focus-visible, STOP 클릭 target ≥44px, 고정 STOP의 화면 안 위치, overflow 없음 확인.
- 토큰 대비: text/surface 13.94:1, muted/surface 7.82:1, cyan/surface 9.07:1, strong boundary/background 4.19:1. 전체 기존 canvas annotation과 모든 legacy 색 조합의 대비 인증은 하지 않았다.
- 긴 지도명/서버 오류는 escape/textContent를 사용하며 HTML 실행·가로 overflow를 검사한다. 빈 catalog의 기존 Public demo cloud fallback은 이름을 그대로 표시하고 저장 지도와 구분한다.
- empty/waiting/stale/disconnected/403/503·read-only·disabled·pending/acknowledged/failed는 기존 상태 경로와 신규 fixture로 검사한다. 성공한 STOP 응답도 물리 정지를 확정하지 않는다.
- geometry·대비 증거: `evidence/browser-geometry-contrast.json`.

## 격리와 캡처

`ui_fixture_server.mjs`는 127.0.0.1:4187 static-only server다. FastAPI/ROS/backend/proxy를 시작하지 않는다. Playwright는 기존 endpoint/WS를 in-memory mock으로 처리하고 외부 hostname을 차단한다. UI 데모의 ARM/Navigation 등 mutation 테스트는 mock 요청 기록뿐이다. 실제 ARM·이동·goal·mapping start/save·서비스 변경·운영 배포 없음.

before: 원본 HEAD의 static assets를 git archive로 별도 임시 디렉터리에 추출. after: 이번 working-tree static assets. 같은 fixture `mission-control-v1`, 같은 route·scenario·viewport, font-ready/reduced-motion/650ms 대기 후 실제 screenshot. 픽셀 편집 없음. 14장씩 28장과 manifest를 보존한다. 모든 이미지에 `UI DEMO / SYNTHETIC FIXTURE / 성능·임상·실장비 검증 아님` 표시가 있다.

manifest의 after `92194cad...+working-tree`는 캡처 당시 커밋 전 구현을 뜻한다. 최종 커밋은 이 소스와 캡처를 함께 포함한다. `SOURCE_FINGERPRINT.json`은 최종 static 파일 hash를 기록해 캡처 대상과 커밋된 source를 대조할 수 있게 한다. commit SHA를 생성 전에 지어내지 않는다.

브라우저 console 수집에서 `/api/v1/state`의 503은 disconnected fixture, `/static/data/go2_saved_map.json`의 404는 저장소에 포함되지 않은 optional private offline map이다. 기존 `Public demo cloud` fallback으로 처리된다. 신규 capture는 이 두 조합만 허용하고 다른 HTTP 오류를 assertion한다. 외부 요청·uncaught page error는 0건이다. `before/after-capture-events.json`에 원문을 보존한다.

## 미검증

| 상태 | 항목 |
|---|---|
| NEEDS_HARDWARE | 실제 Go2·Jetson·ROS/DDS·LiDAR·카메라 시간·대역폭·decode·지연·지속 FPS |
| NEEDS_HARDWARE | ARM/deadman/watchdog·lease·물리 STOP 성능과 실장비 acceptance |
| NEEDS_HARDWARE | Nav2 실제 goal 도달, localization 정확도, mapping 실제 산출물 |
| NOT_RUN | 운영 배포·서비스 재시작·모델 활성화·driver 변경·원격 push/PR/merge/release |
| NOT_RUN | Firefox/Safari·screen reader 전체 audit·모든 legacy annotation 대비 검사 |
| FAIL · baseline | 기존 offline registration extended benchmark acceptance 오류 |

FIXTURE 렌더 숫자는 성능 보증이 아니며 기존 제품/모델/실장비 검증 상태를 올리지 않는다.
