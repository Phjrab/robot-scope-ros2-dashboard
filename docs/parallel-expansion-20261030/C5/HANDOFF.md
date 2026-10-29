# C5 UI usability handoff

2026-10-30 KST. **C5의 독립 표시 보정 구현·브라우저 검증 완료. 제품 연결은 보류.**
별도 일반 clone의 `review/20261030-x-c5-ui-usability`에서만 작업했다.
최종 commit SHA와 원격 CI 결과는 제출 영수증/최종 응답으로 확인한다.

## 조사 소스와 경계

| 소스 | 이번에 검사한 SHA |
|---|---|
| 최신 origin/main / 시작 기준 | `5154761bba6fa4f171881e61f986901e2b415ed9` |
| C2 `review/20261029-x-c2-map-ui` | `7625c87ede2489143c44862d883e10fc1791df28` |
| C3 `review/20261029-x-c3-scene-ui` | `5bf58097f4a67806f5515b931a3b8013d65bf01e` |
| C1 `review/20261029-x-c1-services` | `50600c7bce6f5fae743cd836ca1d8ee68d91b05a` |

처음 clone의 각 원격 ref를 한 번 고정하고, 상대 코드는 쓰기 권한을 제거한
`git archive` export에서 읽고 실행했다. [파일별 Git blob/SHA256 대조](../../../experiments/expansion_20261030/c5_ui_usability/source-manifest.json).
main의 AGENTS.md, Navigation Goal URDF·운영 3D HANDOFF, theme/readability/typography
문서와 관련 검사를 읽었다. AGENTS의 기본 main 규칙에는 명시적 별도 브랜치 예외가
있으며 이번 사용자 요청을 따랐다. 사용자 checkout이나 과거 SHA로 reset하지 않았다.

C2/C3 화면은 main에 통합돼 있지 않다. 각각 기존 독립 test host를 사용했고,
main은 기존 static host + dashboard mock backend를 사용했다. 기존 DOM/Canvas와
공식 `go2-official-lite.json`을 사용했다. 알고리즘·서비스·센서·ROS·실제 주행 검증은 아니다.
C1 과거 보고서의 C3 0.1 FAIL과 C3 후속 0.2 결과를 혼동하지 않았다. 이번 기록 재생은
아래 정확한 C3 SHA의 0.2 응답을 그 SHA의 실제 adapter/consumer로 처리했다.

## 재현 후 수정한 문제

| ID / 심각도 | 화면·절차 | 기대 / 실제 / 수정 |
|---|---|---|
| C5-1 / P2 | main Navigation, 390px, GOAL POSE → 지도에서 위치·방향 드래그 | 좌표·목표 정지 자세 설명 전체를 읽어야 한다. 원본은 578px 텍스트를 334px 한 줄에 ellipsis 처리했다. 해당 readout만 줄바꿈; 문자열·좌표는 그대로. |
| C5-2 / P2 | main, 긴 한국어 오류와 64자리 SHA를 failed pipeline 응답으로 수신 | 경고가 화면 안에 있어야 한다. 긴 무공백 문자열이 banner 밖으로 넘쳤다. 경고 문단만 `overflow-wrap:anywhere`. |
| C5-3 / P2 | C2, 2개 지도 선택 → 자동 정합 → 후보 표, dark/light | 표와 필수 검토 안내가 읽혀야 한다. 10–12px 표/버튼, 11px 안내. light 표 본문 대비 2.76:1, 양 테마 header 3.91:1. scoped 글자 크기·44px 버튼과 기존 테마 토큰 적용. 최종 header 13.08/13.34:1, 본문 14.79/14.92:1 (dark/light). |
| C5-4 / P2 | C2, 후보 확인·수락 → 한글 새 PCD 이름 → 저장 | 입력 전에 이름 제한을 알 수 있어야 한다. 원본은 저장 시에만 `Use a new name (letters/numbers/_/-, 1–64).`를 표시했다. 입력 옆에 기존 규칙·운영 미적용 안내와 accessible description 추가. 한글 거절·export 0건은 그대로. |
| C5-5 / P2 | C3, 390px, 표시 레이어·일시정지 조작 | 터치/글자 확대에서 읽고 선택할 수 있어야 한다. 원본 label은 높이 19px·12px 글자, toolbar 약 36.6px. label/action 최소 44px, 주요 설명 14px 이상으로 보정. |

Main에는 드래그 초안 → SEND POSE → 정합 완료 확인 → GOAL POSE/SEND GOAL
순서를 짧게 설명하고, 기존 상태 문구를 `aria-describedby`로 연결했다. helper는
상태를 추정/번역하거나 판단 불가를 정상으로 바꾸지 않는다. STOP·Cancel·확인창,
비활성 gate, 실제 API payload, URDF asset과 지도 좌표·방향은 그대로다.

## 실제 전후 화면

모두 **합성/mock 브라우저 증거**이며 실장비 촬영이 아니다. 각 쌍은 같은 browser,
viewport, theme, fixture와 원본 feature를 사용하고 C5 주입 여부만 다르다.

| 사례 | 수정 전 | 수정 후 |
|---|---|---|
| main 390 dark · 실제 Goal URDF | [전](evidence/chromium-main-390-dark-before.png) | [후](evidence/chromium-main-390-dark-after.png) |
| C2 390 light · 비교·검토·저장 | [전](evidence/chromium-c2-390-light-before.png) | [후](evidence/chromium-c2-390-light-after.png) |
| C3 390 dark · 레이어·상태 | [전](evidence/chromium-c3-390-dark-before.png) | [후](evidence/chromium-c3-390-dark-after.png) |
| 긴 오류 / 큰 글자 | [전](evidence/chromium-long-error-before.png) | [후](evidence/chromium-long-error-after.png) |
| WebKit main 768 light | [전](evidence/webkit-main-768-light-before.png) | [후](evidence/webkit-main-768-light-after.png) |
| Chromium C2 1440 dark | [전](evidence/chromium-c2-1440-dark-before.png) | [후](evidence/chromium-c2-1440-dark-after.png) |

C3 전체 viewport의 기존 공식 URDF·Canvas도 [1440 dark 전](evidence/chromium-c3-full-1440-dark-before.png) / [후](evidence/chromium-c3-full-1440-dark-after.png), [390 light 전](evidence/webkit-c3-full-390-light-before.png) / [후](evidence/webkit-c3-full-390-light-after.png)로 비교한다. 정지된 표시 snapshot은 장비 최신 상태 증거가 아니며 C5-H1을 참조한다.

나머지 캡처와 실측값은 [browser-results.json](evidence/browser-results.json)에 대응한다.
Canvas 투영은 동일하며 폰트/간격 증가에 따른 페이지 높이 변화는 의도된 reflow다.

## 검증 결과

- Chromium / Playwright WebKit: **36/36 화면 조건 + 15/15 흐름·보존 검사 PASS**.
  3개 화면 × 390/768/1440px × dark/light × 2엔진.
- 2× DPR, 200% root 글자 크기, 긴 한글/오류/SHA, resize, 키보드, touch tap,
  Chromium emulated touch 지도 drag를 검사했다. touch drag 중 페이지 scroll 없음,
  전후 pose 동일. 실제 iPhone Safari/터치 장비·OS 확대 검증은 **NOT_RUN**.
- 원본과 C5 적용 후 실제 공식 URDF XY/yaw와 mock goal payload가 동일하다.
  drag·resize·helper 주입 시 mutation **0**. 확인창 취소 **0**, 명시 확인 후 goal
  **1**. 기존 원본 URDF 검사에서 initial/goal·fallback·지도 revision 방어도 확인했다.
- 초기 정합 ALIGNING → BLOCKED → 완료, 연결 단절 → 재연결, C2 empty/loading/error/
  retry/분리 후보/명시 검토/새 사본 저장, C3 obstacle → supplied costmap/path generation/
  trajectory·위험 원문·calibration/clock/stale·context 단절을 검사했다. supplied path 변경은
  native replanning 성공 증거가 아니다. C2 mock save의 `activate:false` 및 운영 미적용 유지.
- C3 원본 기록 재생 **8/8 PASS** (4응답 × 2엔진): ADVISORY_ONLY와 ACTIVE_CONSTRAINT,
  UNKNOWN/HOLD, EXPIRED, REPLAY/SYNTHETIC을 그대로 표시한다. 실제 센서 LIVE를 만들지
  않았다. bulk geometry 없는 응답은 unavailable이며 생성하지 않았다.
  [기록·원본 응답 hash](evidence/peer-review.json).
- 기존 main 브라우저 회귀: 첫 유효 실행 **52/54**, 포트 환경변수 누락으로 실패한
  popup/origin 2개를 원래 assertion 그대로 올바른 포트로 재실행해 **2/2 PASS**.
  [전체](evidence/regression.log), [2개 재실행](evidence/regression-port-rerun.log).
  단일 실행 54/54라고 기록하지 않는다.
- 공용 JavaScript **700/700 PASS**. 고정 C2 unit/DTO **20/20**, C3 unit **38/38 PASS**.
  C2의 외부 DTO 검증에는 이번 C1 SHA의 실제 Python validator를 사용했다.
- JS syntax **113 modules PASS**, Ruff PASS, mypy **4 files PASS**.
- 전체 Python 최종 직렬 실행: **3132 run / 3128 PASS / 4 SKIP / 0 failure/error**, 130.439초. [최종 로그](evidence/python-final.log). Skip은 optional SVG plotting, rosbags, Linux process sessions /proc, Linux fd inventory 각 1개다.
- 제출 전 소유 범위 검사, tracked-source secret scan, whitespace 검사 PASS. [범위](evidence/scope.json), [secret scan](evidence/secrets.log).

초기 browser harness의 pause rAF 대기, mock endpoint/state명 오류와 이후 long-error
overflow는 [첫 실행](evidence/browser-initial.json), [두 번째](evidence/browser-second.json)에
보존했다. [세 번째](evidence/browser-third.json)는 36/36+12/12 통과였으며 이후 시각 QA에서
C2 대비 결함을 확인해 수정하고 최종 전체 검증/추가 3개 검사를 수행했다. assertion이나
타임아웃을 완화하지 않았다. 시스템 Python 3.13 첫 검사는 의존성 누락/임시경로 문제로
2297 run, 1 failure, 144 errors, 13 skips였다. Python 3.12 첫 전체 실행은 3132 run / 8 failures / 4 errors / 4 skips였다([로그](evidence/python-env-first.log)). macOS temp group wheel/staff 차이 9건과 연산시간/callback 3건을 분리했고, temp group만 보정한 후 관련 71개를 그대로 재실행해 통과했다([로그](evidence/python-isolated-final.log)). 이후 다른 브라우저 작업 없이 전체를 다시 실행해 위 최종 3132 결과를 얻었다. 변경하지 않은 source와 같은 assertion/timeout을 사용했으며 과거 실패를 삭제하지 않았다.

## 다른 담당에게 넘길 결함

**C5-H1 · C3 · P1: 일시정지한 화면의 FRESH/위험이 원래 만료 후에도 유지됨.**

- 정확한 소스: C3 `5bf58097…`, `features/obstacle_scene/index.js:140–145`,
  `snapshot: () => displayed`. `consumer.snapshot()`은 호출되지만 paused + ready일 때
  `displayed`를 갱신하지 않아 이전 pose/joint/risk와 age 표시가 남는다.
- 재현: 기존 fixture `multi` → 표시 일시정지 → 2.6초 경과. Chromium/WebKit 모두
  `Pose · FRESH / Joints · FRESH`, CAUTION, URDF visible=true 유지. 동일 packet을 원본
  C3 consumer로 2500ms 진행하면 `STALE`/만료로 판정된다.
- 기대: 재생 일시정지와 현재 유효성을 구분해 오래된 snapshot이라는 점을 명시하거나,
  원래 freshness 정책대로 위험·URDF를 차단해야 한다. 어떤 정책을 채택할지는 C3 소유다.
- [Chromium 화면](evidence/chromium-paused-expired-original.png),
  [WebKit 화면](evidence/webkit-paused-expired-original.png), [재현 데이터](evidence/peer-review.json).
- **수정하지 않았다.** C5 helper가 freshness를 다시 계산하거나 숨기면 소유권과 계약을
  침범한다. 현재 label은 PAUSED를 표시하며 실제 제어 영향은 관측하지 않았다.

C1의 ancestry 상세 거절 사유 누락은 C2 인계에 있는 기존 항목으로 읽었으며 이번에
실제 service composition을 재실행하지 않았으므로 새 재현 결함으로 집계하지 않았다.

## 수정 경로와 연결

실제 production 후보는 `static/features/operator_usability/{index.js,operator_usability.css}`
두 파일이다. 나머지는 소유 tests/experiment/docs뿐이다. 공용 코드와 상대 feature는
변경하지 않았다. [연결 지점](INTEGRATION_POINTS.md), [재현 절차](../../../experiments/expansion_20261030/c5_ui_usability/README.md).
제품은 새 module을 import하지 않으므로 이 브랜치만 배포해도 제품 화면이 바뀌지 않는다.

로봇 SSH/HTTP/DDS, 카메라·실센서, 실제 Nav2 goal/initialpose/속도·자세 명령,
배포/서비스 재시작, main merge, PR, 다른 브랜치 push는 수행하지 않았다.
새 채팅이나 하위 에이전트도 만들지 않았다.

증거 로그는 Git whitespace 검사를 위해 줄 끝 공백과 마지막 빈 줄만 정리했다. 테스트 결과·오류 내용은 보존했다.
