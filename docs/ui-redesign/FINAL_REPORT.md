# Robotics Mission Control · 최종 UI 보고

대상: `Phjrab/robot-scope-ros2-dashboard` · branch: `codex/ui-robot-scope-mission-control` · baseline: `92194cad2f2f91add260791f2e73f86db6bcbd20`.

## 01~06 결과

1. **Audit**: 실제 registry/lifecycle/카메라 demand/layout/안전·map/nav 경로 조사. 시작 clean checkout와 fixture baseline 확보. [기능 보존표](INVENTORY.md), [baseline](BASELINE.md).
2. **Design system**: styles.css에 단일 공통 palette/type token 계층. 72px rail, 48px 상태바, 328px inspector, 36px strip. 기존 앱의 기본 route를 Mission Control Cockpit으로 연결.
3. **Core**: registry/schema v1을 사용하는 Observation/Mapping/Navigation/Dataset Capture. 기존 applied/default layout 우선·Saved layout 표시. Edit/Apply·armed lock 유지. Inspector는 기존 snapshots만 읽는다.
4. **Remaining screens**: Mapping/Saved Maps/Navigation/Capture를 기존 renderer + 도구 inspector로 재배치. Saved Maps 검색/revision 표시. 모든 기존 hash 및 Advanced 경로 유지. 단일 Safety HUD/STOP을 전체 route에 노출.
5. **Validation**: 기존 unit/브라우저·신규 fixture 테스트, 반복 20회 preset·resize/reload·카메라 reconnect/cleanup·migration·read-only·denied mock ARM·STOP 결과 구분, 실제 before/after screenshot. 정확한 결과와 한계는 [VALIDATION](VALIDATION.md).
6. **Delivery**: 문서·캡처·rollback·실행 방법과 자신의 변경만 feature branch 로컬 커밋. 이 보고서가 포함된 commit은 `git log -1 --format=%H`로 확인한다. 원격 publication·배포는 실행하지 않았다.

## 테스트 요약

- JavaScript unit 340/340, Cockpit unit 107/107.
- 기존 mock E2E 67/67 (Cockpit 21 포함), 신규 Mission Control E2E 8/8.
- architecture Python 5/5. 전체 Python 1483 tests 중 1481 PASS, 기존 error 1, skip 1.
- before/after 14장씩 28장. desktop/tablet/mobile 실제 캡처·source/provenance manifest 보존.
- 실장비 제어·센서 성능·Nav2/매핑 acceptance는 NEEDS_HARDWARE. 운영 배포는 NOT_RUN.

## 실제 변경 파일

- `robot_dashboard/static/index.html`, `styles.css`, `dashboard-polish.css`, `mission-control.css`: shell/단일 token/반응형·읽기 쉬운 안전 영역.
- `features/cockpit/mission_{presets,inspector,shell}.js`, `workspace.js`: preset·저장값 복원·snapshot inspector·route 문맥.
- `app.js`, `scene3d.js`, `scene_host.js`, camera panel/view, safety HUD view: 출처 표시·단일 status poll·STOP 피드백·장면 typography. 제어 API/payload/timeout·backend 변경 없음.
- `scripts/ui_fixture_server.mjs`, `playwright.ui-redesign.config.mjs`, `tests/e2e/ui_redesign*`, 기존 backend optional fixture: 격리 실행/캡처·브라우저 회귀.
- 기존 Cockpit E2E는 신규 기본 camera와 우측 HUD로 바뀐 배치에 맞춰 focus·경계·명시적 Apply 순서를 수정했다. 제어/구독/gate assertions를 삭제하지 않았다.

## 대표 before / after

동일 synthetic fixture로 실제 앱에서 촬영했다. before의 옛 화면에 나타나는 LIVE 표시는 원본 제품의 표시이며 fixture banner가 출처를 명확히 한다. 새 화면은 metadata 기반 FIXTURE/STALE/REPLAY를 구분한다.

| 시나리오 · 1440×900 | Before | After |
|---|---|---|
| Observation | [원본](captures/before/observation-1440x900.png) | [Mission Control](captures/after/observation-1440x900.png) |
| Navigation readiness | [원본](captures/before/navigation-1440x900.png) | [새 화면](captures/after/navigation-1440x900.png) |
| Saved Maps | [원본](captures/before/maps-1440x900.png) | [새 화면](captures/after/maps-1440x900.png) |
| Capture | [원본](captures/before/capture-1440x900.png) | [새 화면](captures/after/capture-1440x900.png) |
| Disconnected | [원본](captures/before/disconnected-1440x900.png) | [새 화면](captures/after/disconnected-1440x900.png) |

1366×768의 동일 5개 시나리오, 1024×768·390×844의 Observation/Disconnected도 보관했다. [Capture manifest](captures/CAPTURE_MANIFEST.csv). 캡처는 UI 검증이며 성능·실장비 성공 증거가 아니다.

## 재실행

Node/Playwright가 저장소 lockfile대로 준비된 환경에서:

```sh
npm run test:unit
npm run test:cockpit
npm run test:cockpit:e2e -- --reporter=line
npx playwright test -c playwright.ui-redesign.config.mjs --reporter=line
```

마지막 명령이 isolated fixture를 브라우저에서 실행하고 after captures도 갱신한다. 실제 backend/로봇이 필요하지 않다. 단독 `node scripts/ui_fixture_server.mjs`는 정적/offline UI만 제공하며 센서 mock은 Playwright 세션에서 공급한다. 기본 E2E config와 신규 config의 포트/trace output을 분리했다.

before 재현은 기준 HEAD의 `robot_dashboard/static`을 임시 디렉터리에 `git archive`로 추출한 뒤 `UI_BASELINE_STATIC_DIR=<추출된-static-절대경로> UI_CAPTURE_PHASE=before npx playwright test -c playwright.ui-redesign.config.mjs --grep 'actual route captures' --reporter=line`으로 수행한다. before 후 after를 촬영하면 manifest에 두 phase가 남는다.

[Rollback](ROLLBACK.md) · [설계 결정](DECISIONS.md) · [인수 기준](ACCEPTANCE.md) · [인계](HANDOFF.md).
