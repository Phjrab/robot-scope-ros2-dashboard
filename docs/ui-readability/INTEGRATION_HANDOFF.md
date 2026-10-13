# 내부 Jetson 마이그레이션 담당 인계 — UI 가독성 개선

## 통합 대상과 식별자

이 변경은 기존 기능을 유지하는 UI 개선이다. 내부 Jetson 마이그레이션, main 통합 및 운영 배포는 이 작업에서 수행하지 않았다. [전후 비교](COMPARISON.html), [감사 기록](AUDIT.md), [검증 기록](VALIDATION.md)을 함께 확인한다.

| 항목 | 값 |
| --- | --- |
| 저장소 | `https://github.com/Phjrab/robot-scope-ros2-dashboard` |
| UI base SHA | `42c6cce986029548e5cc7e0f6f9bd830144cabe3` |
| 최종 UI 코드 SHA | `95d13e214746f4c866cb71b249b9c5dc9b3d0c00` |
| 원격 브랜치 | `origin/codex/ui-readability-refinement` |
| 독립 작업 폴더 | `/Users/hajoonpark/Documents/자율설계/robot-scope-ui-readability` |
| 조사 시 원격 main | `3ec4cc6283e7ba8dd0b1de5b66a81c08dad545c9` |
| 인계 메타데이터 tip | 구현 이후 이 문서를 확정하는 문서 전용 후속 commit. UI 코드 SHA와 구분한다. |

UI 적용 대상은 위 구현 SHA 하나다. 이 문서를 추가하는 후속 commit은 인계 메타데이터만 담으며 운영 코드가 같다. 원격 tip과 문서 commit의 정확한 SHA는 발행 시 최종 사용자 보고 및 아래 Git 조회 결과로 함께 제공한다.

이번 작업에서 만든 UI 구현과 문서의 순서는 다음과 같다. 과거 UI commit은 이 목록에 포함되지 않는다.

1. `95d13e214746f4c866cb71b249b9c5dc9b3d0c00`: 이번 프런트엔드 개선, 테스트 및 근거 자료. 통합할 UI 변경의 기준 commit.
2. `Document UI readability integration handoff` 문서 전용 commit: 이 파일만 추가하며 UI 적용 필수 대상은 아니다. 정확한 SHA는 아래 범위 조회의 두 번째 행과 최종 사용자 보고에 기록한다.

통합 직전에 `git log --reverse --format='%H %s' 42c6cce986029548e5cc7e0f6f9bd830144cabe3..origin/codex/ui-readability-refinement`으로 실제 새 commit 목록과 순서를 대조한다. 진행 중인 마이그레이션 checkout에서 무조건 pull/switch하거나 미커밋 변경을 덮어쓰지 않는다. 이 문서는 자동 merge·cherry-pick·배포 승인을 뜻하지 않는다.

## 기존 UI 선행 조건

다음은 base에 이미 포함된 기존 UI 이력이다. **새로 적용할 commit 목록이 아니며**, 오래된 UI 브랜치 전체를 합치거나 이 목록을 통째로 cherry-pick하라는 지시가 아니다.

| 기존 commit | 포함된 기능 |
| --- | --- |
| `72ee6e2cefee2d734df4fda7c7f899803c407b8d` | Robotics Mission Control 화면과 기존 Cockpit 구성 |
| `823c900587f8d0efd1231273d0caff98f725f66a` | 지속되는 다크/라이트 테마 |
| `b0a2f691b1dc55c2d61e3030bfb4a1fad2a97a8e` | dropdown·텍스트 입력 높이 정렬 |
| `544e108d00538af184f1cb15e8bbe565171962d5` | 자체 호스팅 IBM Plex 서체와 타이포그래피 |
| `42c6cce986029548e5cc7e0f6f9bd830144cabe3` | 위 UI의 당시 Jetson 배포·복구 검증 문서 |

조사 당시 원격 main은 선행 UI를 포함했고, base와 main의 `robot_dashboard/static`은 동일했다. [배포 문서](../ui-typography/DEPLOYMENT.md)의 `544e108`은 2026-10-07의 과거 운영 근거다. 이번 작업은 운영 Jetson을 조회하거나 재배포해 이를 확인하지 않았다. 통합 시에는 마이그레이션 결과의 현재 코드와 비교해 필요한 전제만 확인한다.

## 변경 파일과 범위

경로의 공통 접두사는 표에 명시한다. static 폴더 전체를 복사해서 덮어쓰지 않고 새 commit의 파일/함수/스타일 블록 단위 변경을 통합한다.

| 경로 | 변경 범위 |
| --- | --- |
| `robot_dashboard/static/index.html` | 한국어 메뉴·제목, 일관된 SVG, 메뉴/작업 정보/패널 선택 토글, 상단 센서 요약 배치. 기존 DOM ID·route·입력값 유지. |
| `robot_dashboard/static/styles.css` | 검정·초록 및 대응 라이트 팔레트, 공통 타이포그래피 토큰, 기본 메뉴 폭. |
| `robot_dashboard/static/mission-control.css` | 관측 장면·카메라·Inspector·Safety 영역, 편집 도구, 메뉴와 공통 페이지의 반응형 배치. |
| `robot_dashboard/static/themes.css` | 기존 컴포넌트의 테마 어댑터 및 실제 확인한 도움말 대비. |
| `robot_dashboard/static/typography.css` | Sans/Mono 역할, 15–16px 본문·조작, 18px 패널 제목, 16px 중요 상태. 카메라 상태의 중복 12px 규칙 정리. |
| `robot_dashboard/static/features/cockpit/mission_shell.js` | 표시용 페이지 제목. 내부 route/hash 유지. |
| `robot_dashboard/static/features/cockpit/mission_inspector.js` | 상단으로 옮긴 센서 필드 조회, 한국어 상태와 펼칠 수 있는 기술 원문. |
| `robot_dashboard/static/features/cockpit/mission_presets.js` | 기본 관측 카메라 패널의 UI 좌표·크기. 저장 레이아웃 삭제/변환 없음. |
| `robot_dashboard/static/features/cockpit/status_labels.js` | 알려진 상태·주행 차단 코드의 표시 매핑. 미확인 코드 보존. |
| `robot_dashboard/static/features/cockpit/panels/camera_panel_view.js` | 상태 문구, 주요 3개 수치와 접을 수 있는 전송 상세. 프레임 처리·clear 조건 유지. |
| `robot_dashboard/static/features/cockpit/safety_hud_view.js` | 상시 상태 요약·STOP, 한국어 라벨, 직접 여는 기존 배치 편집. |
| `robot_dashboard/static/features/cockpit/safety_hud.js` | 표시용 null 숫자 처리와 미확인 배터리 표시. authoritative 제어 gate 변경 없음. |
| `robot_dashboard/static/features/cockpit/competition_status.js` | 운영 상세 버튼·제목 라벨. |
| `robot_dashboard/static/features/cockpit/sensor_launcher.js` | disclosure의 `data-expanded`, 패널 선택 버튼과 `aria-expanded` 동기화. |
| `robot_dashboard/static/features/cockpit/workspace.js` | 메뉴/Inspector/패널 선택 표시 listener, 편집 진입 시 Safety 상세 닫기. 기존 controller와 listener 정리 수명 사용. |
| `robot_dashboard/static/app.js` | `navigationBlockerMessage()`의 표시 모듈 호출, `renderNavigationStatus()`의 한국어 제목·원시 차단 상태 유지. |
| `tests/e2e/{dashboard,layout,layout_apply,mission_page,ui_redesign,ui_typography}.spec.mjs` | 의도한 문구·도구 노출·배치 변화 반영. lifecycle·제어·저장값·구독 회귀 assertion 유지. |
| `tests/e2e/static_server.mjs` | UI 검사용 분리 loopback 포트를 환경변수로 선택. 기본값 보존. 운영 서버 아님. |
| `tests/test_{cockpit_safety_hud,cockpit_workspace,dashboard_polish,typography,ui_status_labels}.mjs` | 새 크기·라벨·unknown 표시 검증. 기존 안전/행동 assertion 보존. |
| `docs/ui-readability/` | 전용 fixture 서버·Playwright 설정·검사·AUDIT/VALIDATION/인계·전후 캡처·근거. |

후반 회귀검사에서 자율주행 활성 중에는 기존 안전 gate가 배치 편집을 잠그므로 숨겨진 패널에 접근하기 어려운 문제가 확인됐다. 관측 모드의 **패널 선택** 버튼은 기존 launcher의 열기/선택/focus 경로를 표시해 접근을 복원한다. 활성 Nav 상태에서도 배치 편집 잠금은 유지한다. 제어 권한이나 주행 gate를 완화하는 변경이 아니다.

## 충돌 가능성이 높은 통합 접점

1. `app.js`의 import 목록, `navigationBlockerMessage()`, `renderNavigationStatus()`. 마이그레이션에서 상태 enum이 추가/변경됐다면 원시 enum을 보존한 채 표시 사전만 대조한다. 새 backend 사유를 추측하지 않는다.
2. `workspace.js`의 `createCockpitWorkspace()` 초기 listener와 launcher 생성, `onRequestEdit`. `AbortController` cleanup과 기존 panel/layout controller 소유권을 유지한다. 새 토글은 센서 start/stop이나 요청 payload를 직접 실행하지 않는다.
3. `index.html`의 `missionPresetBar`, `missionInspector`, `cockpitPanelsToggle`, `cockpitInspectorToggle`, `navigationToggle`. Inspector 필드가 이동했으므로 `.cockpit-workspace` 기준 조회와 함께 통합한다.
4. `.cockpit-overlay-layer`, `.cockpit-panel-layer`, `.cockpit-safety-*`, `.inspector-sensor-status`, 메뉴·테마 토큰. 좁은 화면에서 Safety 영역과 장면의 실제 높이를 재검사한다. 편집 library/launcher는 자체 스크롤을 유지한다.
5. `safety_hud.js`의 `finite()`/`projectSafetyHud()`: null·빈 문자열·boolean이 0으로 표시되지 않는지 확인한다. `layoutArmed`와 ARM/deadman/watchdog/lease 판단을 UI 문구 개선 때문에 변경하지 않는다.
6. `mission_presets.js`의 기본 패널 좌표와 이미 저장된 레이아웃. 기존 저장값은 보존하며 호환성을 강제 데이터 삭제로 해결하지 않는다.

## API·ROS·제어·운영 설정

API endpoint·payload·enum, Python backend, ROS 메시지/토픽/QoS/DDS, 네트워크·센서 driver, 제어 브리지·명령 서명, ARM/deadman/watchdog/lease 로직, sensor transport·구독·재접속 정책, deploy/서비스/설치·실행 스크립트, OS/JetPack/CUDA 및 실장비 지도·모델·runtime state는 변경하지 않았다. UI 편집을 위해 FPS·해상도·point budget·구독 주기를 바꾸지 않았다.

현재 backend 계약을 사용하는 표시 개선이며 새 API 의존성은 없다. main/migration 브랜치에 직접 commit/push하거나 운영 Jetson을 조작하지 않았다. 공통 PROJECT_STATE와 마이그레이션 문서는 편집하지 않았다.

## 검증 결과와 재실행

확인 가능한 로그 기준의 결과다. commit 직전 상태 및 상세 명령의 최종 근거는 [VALIDATION.md](VALIDATION.md)에 기록한다.

- Python 전체 unittest: **PASS**, 1483개 실행·1개 skip. `evidence/python.txt`.
- JavaScript 전체 unit: **PASS**, 346/346. 표시 관련 후속 unit: **PASS**, 34/34. 각각 `evidence/unit.txt`, `evidence/targeted-unit.txt`.
- 기존 67개 browser 회귀의 전체 실행은 66/67이며, 중간 패널 좌표 변경의 저장 복원 차이는 해당 변경을 제거해 수정했다. 최종 Cockpit 영향 범위 23개 중 20개 통과, 동시 캡처 실행 중 20초 전체 제한에 걸린 3개는 코드·assertion·제한을 그대로 두고 단독 재실행하여 **3/3 PASS (11.7 s)**. 전체 실행과 수정 후 영향 범위 검사를 합쳐 미해결 실패가 없다. 단일 최신 실행의 67/67이라고 표기하지 않는다. `evidence/regression-accepted.txt`, `regression-cockpit-final.txt`, `regression-isolated-final.txt` 참조.
- 기존 UI 상태·STOP mock 응답·오류 이스케이프·구버전 레이아웃 보존·폰트 재도색 lifecycle: **PASS**, 8/8. `evidence/behavior.txt`.
- 전용 가독성 browser suite: **PASS**, 4개 검사에 12개 캡처 조건, 실제 렌더링 폰트/대비, 편집·구독·저장값, DPR2 포인터가 포함된다. 최종 패널 선택·카메라 수치 배치에서 통과했으며 native 상세 펼치기/접기 추가 1개 검사도 통과했다.
- **NOT_RUN:** 실제 Safari/iPad/터치 하드웨어, 실제 OS/browser 200% 확대, 실장비 센서 성능·대역폭·운영 제어·Jetson 배포. 720×450은 1440×900의 200% CSS reflow 상당 검사이며 실제 iPad 검증이 아니다.

테스트는 UI 전용 clone과 mock/fixture에서 실행한다. 다른 개발 서버를 재사용하거나 종료하지 않는다. 사용 중이면 환경변수로 별도 빈 loopback 포트를 고른다.

```sh
.venv/bin/python -m unittest discover -s tests -v
npm run test:unit
npx playwright test --config docs/ui-readability/playwright.regression.config.mjs --reporter=line
npx playwright test --config docs/ui-readability/playwright.config.mjs --reporter=line
```

Python 검사는 저장소의 격리된 테스트 환경을 사용한다. 전용 가독성 서버 기본 포트는 4198, 기존 browser 회귀 서버/보안 probe 기본 포트는 4199/4200이다. 출력은 `/private/tmp/robot-scope-ui-readability-*`에 격리된다. 재현 상세와 fixture provenance는 VALIDATION을 따른다.

통합 후 다시 확인할 항목:

- 위 Python·JS·browser 회귀검사를 마이그레이션 통합 코드에서 실행한다. 실제 로봇 endpoint로 fixture 검사를 바꾸지 않는다.
- 다크/라이트 1440×900, 1280×800, 1024×768 및 혼잡한 세로/짧은 화면에서 STOP, 상태·차단 사유, 불필요한 가로 스크롤을 확인한다.
- 카메라·pointcloud 단일 구독과 화면 이탈 정리, renderer 수, DPR·canvas 크기·pan/zoom·포인터 hit test를 확인한다.
- 메뉴/Inspector/패널 선택, 편집·이동·resize·lock·restore, 저장 레이아웃 및 theme 보존을 확인한다. 특히 활성 Nav와 수동 lease 잠금 중 기존 표시 패널 선택을 확인한다.
- 모의 ARM/STOP·deadman·watchdog·수동/자율 상호 배제 assertion, map annotation/crop/revision 및 기존 키보드·게임패드 계약을 보존한다.
- migration 결과가 제공하는 연결/LowState/카메라/주행 상태와 표시 사전을 대조한다. unavailable·stale·unknown을 정상이나 0으로 보이지 않게 한다.

## UI만 되돌리는 방법

통합 담당이 이번 구현을 별도 commit으로 적용했다면 **그 통합 commit만** 새 revert commit으로 되돌린다. cherry-pick되면 원본 `95d13e214746f4c866cb71b249b9c5dc9b3d0c00` 대신 통합 저장소에서 생성된 해당 UI commit SHA를 사용한다.

```sh
git revert <통합된_UI_구현_commit_SHA>
```

문서 전용 후속 commit은 운영 코드에 영향을 주지 않으므로 필요에 따라 별도로 보존하거나 revert한다. 과거 UI 기준선·마이그레이션 commit을 묶어 되돌리거나 reset/force push하지 않는다. UI 롤백에 사용자 localStorage 레이아웃·테마, 운영 지도·센서 데이터 삭제가 필요하지 않다. 마이그레이션 코드가 이 UI DOM/함수를 후속 변경했다면 해당 충돌만 검토해 역적용한다.

## 마이그레이션 채팅에 전달할 요청문

> UI 전용 브랜치 `codex/ui-readability-refinement`의 새 UI 구현 commit `95d13e214746f4c866cb71b249b9c5dc9b3d0c00`를 검토해 내부 Jetson 마이그레이션 결과에 통합해 주세요. 기준선은 `42c6cce986029548e5cc7e0f6f9bd830144cabe3`이며 조사 당시 main은 기존 UI를 이미 포함했습니다. 과거 UI 브랜치 전체 merge나 static 폴더 덮어쓰기는 하지 말고 이번 commit의 변경만 통합해 주세요. `docs/ui-readability/INTEGRATION_HANDOFF.md`, `VALIDATION.md`, `COMPARISON.html`에 충돌 접점과 검증 근거가 있습니다. API·ROS·제어·deploy 계약은 변경하지 않았고 운영 배포는 하지 않았습니다. 통합 후 명시된 회귀검사를 재실행한 뒤 운영 배포를 판단해 주세요.
