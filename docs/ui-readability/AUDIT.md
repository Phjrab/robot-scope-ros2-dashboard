# UI 가독성·시각 구성 감사 기록

## 작업 분리와 기준선

- 작업 폴더: `/Users/hajoonpark/Documents/자율설계/robot-scope-ui-readability`
- UI 전용 브랜치: `codex/ui-readability-refinement`
- UI base SHA: `42c6cce986029548e5cc7e0f6f9bd830144cabe3`
- 저장소: `https://github.com/Phjrab/robot-scope-ros2-dashboard`
- 확인한 원격 main: `3ec4cc6283e7ba8dd0b1de5b66a81c08dad545c9`

독립 clone에서 작업했다. 기존 마이그레이션 checkout의 브랜치·작업 파일·미커밋 변경을 가져오거나 변경하지 않았다. 저장소 AGENTS.md의 단일 브랜치 규칙에는 이번 사용자 지시의 UI 전용 브랜치·독립 checkout·해당 브랜치에 대한 commit/push 예외를 적용한다. 보안, 사용자 변경 보존, 검증 규칙은 유지한다.

기준선은 기존 `codex/ui-robot-scope-mission-control` 끝 커밋이다. 이 커밋에는 Mission Control 관측 화면, 저장 레이아웃, 다크/라이트 테마, 입력 높이 보정, 자체 호스팅 IBM Plex Sans/Sans KR/Mono 타이포그래피가 포함된다. [2026-10-07 배포 기록](../ui-typography/DEPLOYMENT.md)은 UI 커밋 `544e108d00538af184f1cb15e8bbe565171962d5`와 당시 release 검증을 기록하며, base `42c6cce`는 그 배포 기록을 추가한 후속 커밋이다. 이 문서는 과거 배포의 근거이며 현재 장비 상태를 증명하지 않는다. 이번 작업에서는 Jetson에 접근하거나 설치·서비스 재시작을 수행하지 않았다.

확인 시 원격 main도 이 UI를 포함했고, `git diff 42c6cce986029548e5cc7e0f6f9bd830144cabe3 origin/main -- robot_dashboard/static`에는 차이가 없었다. 따라서 main에 UI가 빠졌다고 가정하지 않았다. 기존 UI 변화와 이번 변화의 경계를 명확히 하기 위해 확인된 UI 커밋을 독립 기준선으로 선택했고, 진행 중인 마이그레이션 변경을 합쳐 새 기준선을 만들지 않았다.

## 실제 화면에서 확인한 문제

[기존 fixture](../../tests/e2e/ui_redesign_fixture.mjs)를 재사용한 전용 loopback 서버에서 12개 대표 조건을 캡처했다. 기준 자산은 base SHA에서 archive한 파일이다. 동일한 상태·테마·CSS viewport 쌍은 [전후 비교](COMPARISON.html), 원시 측정값은 [before-browser.json](evidence/before-browser.json)에 있다.

| 관찰 | 확인 근거와 영향 | 이번 변경 |
| --- | --- | --- |
| 중요 카메라 상태가 12px로 축소됨 | `typography.css`에서 `.cockpit-camera-state`에 14px를 지정한 뒤 마지막 보조정보 그룹이 12px로 재지정했다. 작은 배지와 주변 기술 정보의 위계가 약했다. | 상태는 16px 역할에 통합하고 중복 12px 규칙에서 제외했다. |
| 기본 메뉴가 72px rail에 의존 | 데스크톱에서도 영문 주 메뉴와 두 글자 약어·문자 기호가 섞였다. 추가 메뉴의 전체 이름은 시각적으로 드러나지 않아 약어 또는 툴팁 해석이 필요했다. 기존 aria-label이 없었다는 뜻은 아니다. | 기본 폭을 확보한 한국어 메뉴와 동일 규격 SVG로 정리하고 명시적인 접기 버튼을 추가했다. 내부 hash·route·data-nav는 그대로다. |
| 관측 화면 도구와 Inspector가 상시 경쟁 | scene toolbar, layout library, sensor launcher, Inspector, Safety HUD가 함께 보이며 장면·카메라에 배분되는 공간을 줄였다. 다른 페이지의 고정 Safety HUD도 지도/설정 영역과 겹쳤다. | 상단 센서 요약, 선택적으로 여는 작업 정보, 기존 편집 모드에서 드러나는 배치 도구, 하단 Safety 영역으로 화면 역할을 나눴다. STOP은 상시 접근 대상으로 유지했다. |
| 제목·설명·상태의 위계가 약함 | 영문 패널 제목, 12–14px 보조 규칙, 일반 상태 문장의 Mono 적용이 섞였다. Mapping·설정 도움말 일부는 토큰 대신 낮은 대비의 고정 회색을 사용했다. | 일반 설명/버튼은 15–16px 중심, 패널 제목 18px, 중요한 상태 16px로 조정했다. 수치·토픽·식별자는 Mono를 유지하고 자연어 상태는 Sans로 표시한다. 확인한 도움말 선택자에는 공통 보조색을 적용했다. |
| 상태 코드의 의미를 바로 읽기 어려움 | Inspector·카메라 상태의 `STALE`, `WAITING`, `NOT_CONNECTED`와 알려진 주행 차단 코드가 기본 표시였다. | 표시 문구는 한국어로 매핑하고 raw 상태는 `data-state`, title 및 기술 상세에 남긴다. 알 수 없는 코드는 정상으로 치환하지 않는다. |
| 미확인 숫자가 0으로 보일 수 있음 | Safety HUD의 표시용 `finite()`가 JavaScript `Number(null)` 변환을 허용했다. | null·빈 문자열·boolean을 표시용 숫자로 받지 않는다. 미확인 배터리는 `UNKNOWN`이며 권한·제어 판단 코드는 변경하지 않는다. |

기준선의 **대표 중요 텍스트 잘림 검사, STOP 접근 검사와 토큰 대비 검사는 이미 통과했다.** 위 관찰을 “기존 STOP이 동작하지 않았다”, “모든 글자가 잘렸다”, “기존 테마 전체가 대비 기준 미달이었다”는 주장으로 확대하지 않는다. 가독성·공간 배분의 실제 문제와 자동검사의 통과 여부를 구분한다.

개선 과정에서는 작은 화면의 장면이 Safety 영역에 가려지는 경우, 편집 library가 좁은 열에 갇히는 경우, 카메라 주요 수치가 패널 아래로 밀리는 경우도 캡처 검토로 발견했다. 카메라 주요 수치는 영상 위로 옮기고 전송 상세는 영상 아래에서 펼치도록 했다. 주행 중 편집 잠금 상태에서도 이미 열린 패널을 선택할 수 있는 상단 버튼을 유지한다. 해당 수정과 최종 실행 결과는 [검증 기록](VALIDATION.md)이 관리한다. 이 문서는 진행 중인 검증을 최종 통과로 선언하지 않는다.

## 시각 방향과 CSS 책임

사용자의 후속 지시는 **검정·초록 기반에 약한 네온 느낌**을 선호한다는 것이었다. 이는 처음 요청의 중립 배경·네온 금지 방향을 수정한 명시적인 선호다. 검정에 가까운 녹색 배경과 밝은 초록 선택 강조를 적용했고, 광범위한 글로우·그림자·장식 애니메이션을 추가하지 않았다. 라이트 테마는 녹색 중립 배경과 진한 초록 강조색을 사용한다. 카메라 픽셀과 점군/지도 원본 색은 테마에 맞춰 변조하지 않는다.

| 토큰 | 다크 | 라이트 |
| --- | --- | --- |
| 배경 `--bg` | `#0b100e` | `#f2f7f3` |
| 보조 배경 `--bg-soft` | `#101813` | `#e7f0e9` |
| 패널 `--panel` | `#16211b` | `#ffffff` |
| 강조 패널 `--panel-strong` | `#1c2c23` | `#edf4ee` |
| 본문 `--text` | `#e9f5ed` | `#192b20` |
| 보조 본문 `--muted` | `#adc2b4` | `#4a6253` |
| 상태 초록 `--green` | `#8cddb1` | `#176440` |
| 강조색 `--cyan` | `#74edaa` | `#09643b` |

`--cyan`이라는 내부 변수명은 호환성을 위해 유지했다. 팔레트의 네 배경 위에서 수학적으로 계산한 보조 본문 최소 대비는 다크 7.78:1, 라이트 5.70:1이며 강조색은 각각 10.07:1, 6.23:1이다. 이는 토큰 조합 계산이며 모든 픽셀에 대한 실측 주장은 아니다. 실제 합성 배경·서체·잘림 검사는 별도 브라우저 근거를 따른다.

스타일 로딩 순서는 `styles.css → cockpit.css → dashboard-polish.css → mission-control.css → themes.css → typography.css`를 유지한다. 새 보정 파일을 덧붙이지 않았다.

- `styles.css`: 공통 팔레트·타입 크기 토큰. 13px 부가정보, 15px 조작/보조정보, 16px 본문, 18px 패널 제목.
- `mission-control.css`: 메뉴·관측·Inspector·Safety·편집 도구의 배치와 반응형 크기.
- `typography.css`: Sans/Mono 역할, 상태 크기, 한국어 줄바꿈. 같은 상태의 중복 크기 재정의를 제거.
- `themes.css`: 기존 고정 배경/텍스트의 다크·라이트 어댑터와 확인된 도움말 대비.
- 기존 `cockpit.css`, `dashboard-polish.css`와 컴포넌트 스타일은 기능별 기반으로 남겨 두었다. 파일 전체 삭제나 포맷 재작성은 하지 않았다.

## 변경 범위와 통합 접점

현재 변경 파일은 다음 역할로 제한한다. 정확한 최종 커밋과 적용 순서는 별도 통합 인계 문서가 기록한다.

| 영역 | 파일 | 범위 |
| --- | --- | --- |
| 공통 화면 | `static/index.html`, `static/styles.css`, `static/mission-control.css`, `static/themes.css`, `static/typography.css` | 표시 문구·SVG·DOM 배치·스타일. 기존 DOM ID 437개와 기계 식별자 유지. |
| Cockpit 표시 | `features/cockpit/mission_shell.js`, `mission_inspector.js`, `mission_presets.js`, `status_labels.js`, `panels/camera_panel_view.js`, `safety_hud_view.js`, `competition_status.js`, `sensor_launcher.js` | 한국어 표시, 기본 패널 배치, Inspector 상세, 표시용 disclosure 상태. 저장 레이아웃을 삭제하지 않는다. |
| 제한된 공통 JS | `static/app.js`, `features/cockpit/workspace.js`, `features/cockpit/safety_hud.js` | 알려진 차단 사유 표시, 메뉴/Inspector listener, 편집 시 Safety 상세 닫기, 미확인 숫자 표시. |
| 테스트·근거 | `tests/e2e/{dashboard,layout,layout_apply,mission_page,ui_redesign,ui_typography}.spec.mjs`, `tests/e2e/static_server.mjs`, `tests/test_{cockpit_safety_hud,cockpit_workspace,dashboard_polish,typography,ui_status_labels}.mjs`, `docs/ui-readability/` | 의도한 문구·도구 노출 변화 반영, 상태/안전 계약 검증, 분리된 fixture·출력·캡처·문서. |

경로 표의 `static/` 및 `features/`는 각각 `robot_dashboard/static/`와 `robot_dashboard/static/features/`를 기준으로 한다.

통합 시 특히 확인할 접점:

1. `app.js`의 `navigationBlockerMessage()`와 `renderNavigationStatus()`: backend가 제공하는 차단 enum과 표시 매핑을 대조한다. 알려지지 않은 원인을 추측해 새 설명을 만들지 않는다. 원시 차단 목록은 남는다.
2. `workspace.js`의 메뉴·Inspector 클릭 listener와 `onRequestEdit`: 기존 `AbortController` 수명 범위와 기존 layout controller를 사용한다. sensor start/stop·재접속·구독 owner는 변경하지 않았다.
3. `missionPresetBar`, `missionInspector`, `.inspector-sensor-status`, `.cockpit-safety-*`, `.cockpit-overlay-layer`: 마이그레이션 브랜치가 같은 DOM 또는 선택자를 바꾸면 함수/블록 단위로 통합해야 한다. Inspector의 센서 요약은 상단으로 옮겨져 조회 범위가 workspace 기준이다.
4. `safety_hud.js`의 `finite()`와 배터리 표시: null이 0으로 표시되지 않는지 재검사한다. ARM·deadman·watchdog·lease의 authoritative 계약은 그대로다.
5. 저장 레이아웃·theme localStorage, Canvas/WebGL 크기·DPR·포인터 좌표: 실제 통합된 화면 크기에서 재검증한다. 기본 preset의 UI 배치 변경이 기존 저장 데이터를 덮어쓰는 방식은 아니다.

Python backend, API endpoint/payload, ROS 토픽·QoS·DDS·네트워크, 제어 브리지·명령 서명, sensor driver/전송/재접속 정책, deploy 및 운영 서비스·실행 스크립트, OS 패키지, 실장비 데이터는 변경 대상이 아니다. FPS·해상도·point budget·구독 주기도 UI를 위해 바꾸지 않았다. 공통 PROJECT_STATE·마이그레이션 문서는 수정하지 않았다.

운영 통합·충돌 해결·배포는 마이그레이션 담당 단계에 남긴다. 오래된 UI 브랜치 전체를 합치거나 static 폴더를 통째로 덮어쓰는 방식은 인계하지 않는다.
