# 화이트 / 다크 모드

상단 버튼으로 전환하며 기본값은 다크입니다. 키보드 Tab → Space/Enter로도
사용할 수 있습니다. 선택은 `robot-scope.ui.theme.v1` localStorage에 저장됩니다.
같은 origin의 다른 창과 Offline Experiments가 설정을 공유합니다. 별도 Cockpit
창은 기존 창 정책대로 상단 헤더를 숨기며, 원래 창에서 바꾸면 함께 전환됩니다.
저장을 사용할 수 없으면 현재 창에서 전환하고 버튼 tooltip으로 안내합니다.
잘못된 저장값이나 설정 삭제 시 다크로 돌아갑니다. OS 테마를 자동 추종하지 않습니다.

CSS 전 로딩하는 `theme.js`가 첫 화면부터 저장된 테마를 적용합니다.
화이트 팔레트와 기존 고정 배경 어댑터는 `styles.css`와 `themes.css`에 있습니다.
테마 전환은 DOM 속성만 바꾸며 카메라/지도 canvas를 재생성하거나 필터링하지 않습니다.

## 기능 보존

| 계약 | 확인 |
| --- | --- |
| Cockpit 패널·저장 레이아웃 | 20회 전환 전후 패널 상태와 테마 외 localStorage 동일 |
| 센서 렌더러 | renderer 1개, pointcloud consumer `cockpit` 유지 |
| 카메라 구독 | 20회 전환 전후 연결·close 수 동일; 기존 카메라 E2E 통과 |
| 안전 제어 | ARM·이동·Nav2 start/goal·매핑 start/save 요청 없음; STOP trial hit test |
| STOP 가독성 | 고정 HUD와 Controls STOP은 화이트에서도 빨간 배경·흰 글자 |
| Experiments | 로컬 파일 읽기 유지; 추가된 유일한 버튼은 UI 테마 전환 |
| 모바일 | 390×844에서 테마와 STOP 접근 가능, 문서 가로 넘침 없음 |

## 검증

격리 loopback fixture 및 mock backend로 실행했습니다. 실제 로봇 제어, 운영 배포,
원격 push는 실행하지 않았습니다.

| 검증 | 결과 | 로그 |
| --- | --- | --- |
| Python 전체 | 1,483개: 1,482 통과, 1 skip, 실패 0 | [python.txt](evidence/python.txt) |
| JavaScript unit | 340 통과 | [unit.txt](evidence/unit.txt) |
| 기존 브라우저 회귀 | 67 통과 | [regression-browser.txt](evidence/regression-browser.txt) |
| 테마 E2E | 3 통과 | [browser.txt](evidence/browser.txt) |

테마 E2E는 20회 전환, 키보드 전환, reload, 별도 창, 저장 불가/잘못된 값,
Experiments 설정 공유, 10개 앱 경로, 두 팔레트, 모바일을 확인합니다.
토큰 대비와 STOP·카메라·데이터셋·Settings·Navigation·Route Planner의 실제
computed foreground/background 대비를 측정해 선택한 글자에 4.5:1 이상을 요구합니다.
[측정 결과](contrast.json). 전체 UI의 WCAG 적합성을 인증하는 검사는 아닙니다.

재실행:

```sh
.venv/bin/python -m unittest discover -s tests -v
npm run test:unit
npm run test:e2e -- --reporter=line
npx playwright test -c playwright.themes.config.mjs --reporter=line
```

## 실제 앱 캡처

24개 PNG: 10개 앱 경로 × 두 테마(1440×900), Cockpit 모바일 × 두 테마(390×844),
Offline Experiments × 두 테마(1440×900). 모두 실제 수정한 앱을 Chromium으로
렌더링한 synthetic fixture 화면이며, 실장비·성능 검증 증거가 아닙니다.
[파일·시각·SHA256 목록](CAPTURE_MANIFEST.json).

| 화면 | 화이트 | 다크 |
| --- | --- | --- |
| Cockpit | [보기](captures/light-cockpit-1440x900.png) | [보기](captures/dark-cockpit-1440x900.png) |
| Navigation | [보기](captures/light-navigation-1440x900.png) | [보기](captures/dark-navigation-1440x900.png) |
| Capture | [보기](captures/light-sensors-1440x900.png) | [보기](captures/dark-sensors-1440x900.png) |
| Settings | [보기](captures/light-settings-1440x900.png) | [보기](captures/dark-settings-1440x900.png) |
| 모바일 | [보기](captures/light-cockpit-390x844.png) | [보기](captures/dark-cockpit-390x844.png) |
| Experiments | [보기](captures/light-experiments-1440x900.png) | [보기](captures/dark-experiments-1440x900.png) |

기존 리디자인의 before/after 증거는 `docs/ui-redesign`에 그대로 보존했습니다.

## 미검증

실제 Go2/Jetson/ROS, 실제 카메라·센서 프레임, 실제 정지 성능·Nav2 goal 도달,
운영 서비스에서의 정적 asset 갱신, Safari/Firefox, OS 고대비 모드는 미검증입니다.

## Rollback

현재 브랜치 `codex/ui-robot-scope-mission-control`의 테마 전용 커밋만 되돌립니다.
공유/운영 서비스 변경 없이 로컬 Git에서 수행합니다.

```sh
git log --oneline --grep='Add persistent light and dark themes' -1
git revert <위에서 확인한 테마 커밋 SHA>
```

기존 Mission Control 커밋 `72ee6e2`와 layout 저장값은 유지됩니다.
필요하면 브라우저 console에서 `localStorage.removeItem('robot-scope.ui.theme.v1')`
후 새로고침해 테마 설정만 지울 수 있습니다. layout key는 삭제하지 않습니다.
