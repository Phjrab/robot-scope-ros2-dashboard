# IBM Plex 타이포그래피

대상 `Phjrab/robot-scope-ros2-dashboard` · branch `codex/ui-robot-scope-mission-control`.
기준은 현재 리디자인·테마·44px 입력 높이가 적용된 `b0a2f69`이다. 기존 main 레이아웃으로 되돌리지 않았다.
색상·패널 배치·기능·API·저장 schema·안전 제어 계약은 유지했다.

## 역할과 크기

| 역할 | family 순서 | 굵기 | 적용 |
| --- | --- | --- | --- |
| `font-ui` | IBM Plex Sans → IBM Plex Sans KR → 시스템 | 400·500·600 | 영문/한글 메뉴, 설명, 버튼, 상태 |
| `font-display` | `font-ui`와 동일 | 600 | 브랜드, 주요 제목 |
| `font-mono` | IBM Plex Mono → IBM Plex Sans KR → 고정폭 대체 | 400·500 | 숫자·좌표·속도·FPS·시간·ROS 토픽·경로·코드·로그 |

일반 설명 14~15px/400/line-height 1.5, 버튼 14px/500, 주요 제목 26px/600
(작은 화면 24px), 패널 제목 16px/600, 기술 데이터 13px/500, 로그 13px/400/1.6,
보조 정보 12px 이상을 사용한다. 기존 밀도 높은 Cockpit 시점 도구는 13px이며
패널의 보조 버튼·라벨은 12px를 유지한다. 전체 패널을 재배치하지 않았다.

혼용 문장 자간은 0이다. 짧은 대문자 eyebrow만 .03em이다. 기술 데이터는
`tabular-nums`, ligature off를 사용한다. KR 문자가 없는 Sans/Mono에서 한글을
Sans KR로 fallback한다. 한글 로그는 `pre-wrap`/`overflow-wrap`으로 감싸며,
한글까지 고정폭이라고 가정한 ASCII 열 정렬을 추가하지 않는다.
`font-synthesis: none`으로 굵기·기울기 합성을 차단했다.

## 공식 배포본과 로딩

출처: [IBM/plex](https://github.com/IBM/plex), 고정 commit
`763c36ef9117782905ae010056dfbe8fd2653a25`.

- `@ibm/plex-sans` 1.1.0: Regular 400 / Medium 500 / SemiBold 600.
- `@ibm/plex-sans-kr` 1.1.0: Regular 400 / Medium 500 / SemiBold 600.
- `@ibm/plex-mono` 2.5.0: Regular 400 / Medium 500.
- 공식 complete static WOFF2 8개를 그대로 사용했다. KR은 complete/hinted 배포본이며,
  가변 폰트·별도 서브셋·문자 제한·파일 변환을 사용하지 않는다.
- 저장소 `/static/fonts/ibm-plex/`에서 same-origin 제공, `font-display: swap`.
  preload 및 런타임 Google Fonts/CDN 요청 없음. 필요한 굵기만 CSS 수요로 로딩한다.
- [출처·버전·원본 SHA256](../../robot_dashboard/static/fonts/ibm-plex/SOURCE_MANIFEST.json).
  SIL OFL 1.1 원본 라이선스 세 파일을 자산과 함께 보존했다.

## 변경 파일

| 파일 그룹 | 변경 |
| --- | --- |
| `static/fonts.css`, `fonts/ibm-plex/` | 정확한 family·weight @font-face, 원본 자산·라이선스·출처 |
| `styles.css`, `typography.css` | 역할 토큰, 폼 상속, Sans/Mono 구분, 굵기·크기·자간 정리 |
| `dashboard-polish.css`, `mission-control.css`, `features/cockpit/cockpit.css` | 기존 시스템/Inter 충돌과 지원하지 않는 굵기·작은 글자 정리 |
| `features/experiments/view.css`, `features/route_planner/schematic.css` | 별도 화면과 편집기 폰트 역할 적용 |
| `index.html`, `experiments.html` | 로컬 face CSS 먼저, 역할 CSS 마지막, deferred typography helper |
| `typography.js` | FontFaceSet ready/loadingdone 후 RAF로 텍스트 paint만 갱신 |
| `scene3d.js`, `live_map2d.js`, `app.js`, `map_annotations.js` | Canvas 역할·크기, 텍스트 실측 폭과 label 높이, 로드 후 repaint |
| `features/cockpit/panels/{map,navigation}_panel.js` | 기존 지도 상태로 repaint, destroy 시 폰트 구독 cleanup |
| `features/perception/result_overlay.js`, `features/route_planner/{competition_map_view,spatial_editor}.js` | 별도 Canvas/SVG·좌표/숫자 라벨 |
| `playwright.typography.config.mjs`, `tests/e2e/ui_typography.spec.mjs` | 격리 capture matrix, CDP·FontFaceSet·숫자 폭·lifecycle 검증 |
| `playwright.config.mjs`, typography/polish unit 기대값 | 별도 fixture spec 분리, 실제 토큰 기대값 갱신 |

폰트로 감기는 카메라 statusline의 gap/wrap, metrics wrap, STOP padding/gap/최소 높이,
launcher 최소 높이만 보완했다. 제목 영역은 기존 줄 안에서 남은 폭을 사용하도록
shrink시켜 패널 버튼이 두 번째 줄로 밀리는 것을 방지했다. 기존 floating panel의
좌표·크기·workspace 높이·resize bounds는 유지한다. API/polling/센서 구독 변경 없음.

## 실제 렌더링과 캡처

[검증 결과·기능 보존표](VALIDATION.md) · [rollback](ROLLBACK.md).
[CDP 렌더링 폰트](evidence/rendered-fonts.json) · [capture manifest](CAPTURE_MANIFEST.json).

48쌍의 동일 viewport·시나리오·테마 before/after와 specimen 1장을 보관한다.
1920×1080 / 1440×900 / 1280×800 × 다크/화이트 × Cockpit, Maps, Navigation,
Missions, Capture, Settings, disconnected(503 오류), stale이다.
숫자/센서 값은 synthetic fixture이며 실측 성능이 아니다. specimen도 서체 확인용 예시로 표시한다.

| 화면 · 1440×900 | Before | After |
| --- | --- | --- |
| Cockpit · 다크 | [보기](captures/before/dark-cockpit-1440x900.png) | [보기](captures/after/dark-cockpit-1440x900.png) |
| Maps · 다크 | [보기](captures/before/dark-maps-1440x900.png) | [보기](captures/after/dark-maps-1440x900.png) |
| Navigation · 화이트 | [보기](captures/before/light-navigation-1440x900.png) | [보기](captures/after/light-navigation-1440x900.png) |
| Missions · 다크 | [보기](captures/before/dark-missions-1440x900.png) | [보기](captures/after/dark-missions-1440x900.png) |
| Capture · 화이트 | [보기](captures/before/light-sensors-1440x900.png) | [보기](captures/after/light-sensors-1440x900.png) |
| Settings · 화이트 | [보기](captures/before/light-settings-1440x900.png) | [보기](captures/after/light-settings-1440x900.png) |
| Disconnected · 다크 | [보기](captures/before/dark-disconnected-1440x900.png) | [보기](captures/after/dark-disconnected-1440x900.png) |
| Stale · 다크 | [보기](captures/before/dark-stale-1440x900.png) | [보기](captures/after/dark-stale-1440x900.png) |

[대표 문자열 specimen](captures/after/specimen-1440x900.png).
