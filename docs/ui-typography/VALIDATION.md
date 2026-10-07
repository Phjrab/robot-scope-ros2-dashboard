# 타이포그래피 검증

로컬 Chromium + same-origin static fixture / in-memory mock API에서 실행했다.
실제 로봇 연결·ARM·이동·Nav2 goal·매핑 시작·운영 서비스 재시작·push·배포는 실행하지 않았다.
기존 E2E에서의 ARM/Nav2/매핑/STOP mutation은 mock 기록이다.
타이포그래피 전용 E2E에서는 실제 제어 액션 없이 STOP trial hit test를 사용하며 위험 요청이 0임을 검증한다.

## 테스트 결과

| 검사 | 결과 | 증거 |
| --- | --- | --- |
| Python 전체 regression | 1,483 실행: 1,482 통과, 1 skip, 실패 0 | [python.txt](evidence/python.txt) |
| JavaScript unit | 340 통과, 실패 0 | [unit.txt](evidence/unit.txt) |
| 기존 browser regression | 67 통과, 실패 0 | [regression-browser.txt](evidence/regression-browser.txt) |
| Typography 최종 suite | 3 통과, 실패 0 | [browser.txt](evidence/browser.txt) |
| 기존 긴 지도명·오류 E2E | 1 통과, 실패 0 | [long-errors.txt](evidence/long-errors.txt) |
| Before capture run | 1 통과, after 전용 검사 2 skip | [before-browser.txt](evidence/before-browser.txt) |

초기 기존 E2E에서는 workspace 높이를 8px 줄여 resize 최대 높이에 도달하는 문제와
폰트 증가로 제목줄 버튼이 다음 줄로 감겨 겹치는 문제, 두 건이 실패했다.
workspace 높이 변경을 제거하고 제목 영역이 기존 줄 안의 가용 폭으로 shrink하도록 수정했다.
기존 E2E의 click/resize/카메라 assertions는 수정하거나 삭제하지 않았으며 최종 두 건 모두 통과했다.

Python skip은 macOS에서 Linux process session과 `/proc`가 필요한 orphan cleanup 검사 1건이다. 실장비·운영 acceptance 검사는 미실행이다.
`document.fonts.check()` 또는 CSS 문자열만으로 적용 성공을 판단하지 않았다.

## 실제 폰트 확인

[CDP raw 결과](evidence/rendered-fonts.json).
`CSS.getPlatformFontsForNode`의 `postScriptName`, `glyphCount > 0`, `isCustomFont`를 확인했다.

| 문자열/실제 UI | 실제 렌더링 |
| --- | --- |
| 로봇 연결 상태 | `IBMPlexSansKR` 한글 + `IBMPlexSans` 공백 |
| Map & Localization / 페이지 제목 | `IBMPlexSans-SmBld` |
| STOP · DISARMED | `IBMPlexSans` (specimen); 실제 STOP 버튼 `IBMPlexSans-SmBld` |
| /camera/image_raw · x: 1.250 m · 15.0 FPS · 0 O 1 I l | `IBMPlexMono` |
| 연결 끊김 · 마지막 수신 시각 (mixed log) | `IBMPlexSansKR` + `IBMPlexMono` 공백·기호 |
| 실제 Settings IP | `IBMPlexMono-Medm` |
| 실제 한글 페이지 설명 | `IBMPlexSansKR` + `IBMPlexSans` 영문/공백 |

원본 폰트 8개와 라이선스 3개의 staging content SHA256이 공식 manifest와 모두 일치한다. 원본 license의 CRLF/공백은 보존했으며, 해당 배포 파일을 제외한 `git diff --cached --check`는 통과했다.

8개 WOFF2 요청 모두 HTTP 200이다. capture 결과의 `fontResponses`와
FontFaceSet loaded 상태·family·weight를 함께 기록했다. `document.fonts.ready` 후 두 번의 RAF와
화면 안정화 시간을 기다려 촬영했다. 외부 폰트 CDN 요청은 없다.
Mono 14px에서 숫자 0~9의 DOM 폭이 모두 8.40625px로 동일했다.
Settings의 `#robotType` select와 `#robotIp` input은 모두 44px이다.
대표 문자열은 specimen 안에 “서체 확인용 예시 / 실측값 아님”으로 표시한다.

Canvas는 기존 draw 루틴에 역할 토큰을 전달하며 측정된 text width를 다시 사용한다.
FontFaceSet 이벤트는 repaint callback만 실행한다. SVG는 역할 font-family를 지정했다.
CDP 결과는 DOM/specimen glyph 검증이며, Canvas의 각 픽셀에서 사용된 font를 CDP로 추출한 결과는 아니다.

## 기능 보존표

| 기능/계약 | 확인 |
| --- | --- |
| Cockpit 수명주기·floating panels | 기존 drag/resize/focus/lock/compact/close/recover, singleton·20회 재진입 E2E 통과 |
| 카메라 구독 | 기존 공유 catalog source·reconnect·stale·close E2E 통과; late font load 후 연결/close 수 동일 |
| 레이아웃 저장·복원 | 기존 Apply/reload/import/migration E2E 통과; 폰트 load 및 20회 loadingdone 후 패널 snapshot와 localStorage 동일 |
| 지도 조작 | 기존 pan/zoom/editor/crop/annotation/revision E2E 통과; 측정·paint만 변경 |
| Navigation/Mission | 기존 readiness/ownership/takeover/draft/rejected start E2E 통과; API/payload/gate 변경 없음 |
| 키보드 입력 | 기존 키보드/gamepad/fail-closed 검사 통과; Layouts 버튼 Space toggle 확인 |
| ARM/deadman/watchdog/STOP | 계약·timeout·control 코드 변경 없음; 기존 unit/Python/mock E2E 통과, 모든 capture에서 STOP trial hit |
| 센서 렌더러 | late font load 및 20회 추가 이벤트 후 renderer 1개·pointcloud consumer `cockpit` 유지 |
| 숫자·폼 높이 | 0~9 동일 폭, select/input 44px 유지 |

[late-load lifecycle 기록](evidence/font-lifecycle.json).

## 화면 검사

[Before geometry](evidence/before-captures.json) · [After geometry/requests](evidence/after-captures.json).
세 viewport × 두 테마 × 8개 시나리오에서 STOP·DISARMED/DEADMAN·연결 상태의
scroll overflow와 viewport 경계, STOP hit target을 검사했다. stale은 최초 frame을 받은 뒤
fixture stream을 멈춰 실제 STALE 전이가 발생한 상태로 촬영한다. disconnected는 fixture 503 오류 상태다.
48개 after 캡처의 세 viewport별 contact sheet를 직접 검토했고, Cockpit before/after 1440×900, stale 1280×800, Maps/Missions/Navigation 1440×900, Capture/Settings 1920×1080 및 specimen 원본을 열어 메뉴 폭·한글 줄높이·지도 라벨·카메라 metrics·페이지 설명을 확인했다.
Layout library popup의 가로 경계와 키보드 열기/닫기를 확인했다.
기존 browser suite는 320~1920px layout 경계, Navigation/Capture/Settings/오류 상태도 검사한다.

revision/path와 좁은 floating panel 제목의 기존 ellipsis는 유지한다. 카메라 이름은 statusline에도 표시된다. STOP/ARM·연결 끊김·stale 경고는 잘림을 허용하지 않는다.
이 검증은 선택한 viewport·fixture의 검사이며 모든 문자열/플랫폼의 시각 적합성을 인증하는 것은 아니다.

## 재실행

```sh
.venv/bin/python -m unittest discover -s tests -v
npm run test:unit
npx playwright test --reporter=line
npx playwright test -c playwright.typography.config.mjs --reporter=line
```

before는 `b0a2f69`의 static 디렉터리를 별도 임시 경로에 `git archive`로 추출한 뒤:

```sh
UI_BASELINE_STATIC_DIR=<추출된-static-절대경로> TYPOGRAPHY_CAPTURE_PHASE=before npx playwright test -c playwright.typography.config.mjs --reporter=line
```

작업트리를 되돌리지 않는다. before 촬영 후 위 after 명령을 실행하면 비교 증거가 갱신된다.

## 미검증 / 미실행

실제 Go2/Jetson/ROS·실카메라/센서 프레임·실제 정지/주행/goal 도달·매핑 시작·
실장비 keyboard/deadman/watchdog 타이밍·운영 정적 asset 캐시/서비스 갱신은 장비 없이 확인하지 않았다.
Safari/Firefox·OS native select popup·시스템 대체 글꼴만 남는 offline asset 실패 상황·모든 유니코드 glyph는 미검증이다.
운영 배포·서비스 재시작·원격 push는 미실행이다.
