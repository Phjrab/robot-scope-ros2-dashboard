# C3 PAUSED freshness 후속 수정

2026-10-30 KST. **C5-H1 재현 → C3 소유 코드 수정 → 실제 Chromium/WebKit 표시 회귀 PASS.**
기존 브랜치 `review/20261029-x-c3-scene-ui`, 시작 HEAD
`5bf58097f4a67806f5515b931a3b8013d65bf01e`. 시작 시 원격 SHA 일치·clean 확인.
새 채팅/브랜치/전체 재구현 없이 진행했다.

## 원인과 표시 정책

`index.js`는 `consumer.snapshot()`을 호출하면서도 paused+ready이면 기존
`displayed`를 계속 렌더링하고 public snapshot도 그 객체를 반환했다.
프레임 선택뿐 아니라 freshness 결과가 고정되어 STALE인 관측이 FRESH로 남았다.

- **PAUSED는 프레임 선택만 고정한다.** 화면에 과거 프레임이며 유효시간은 계속
  경과함을 명시한다. render와 public snapshot read 모두 현재 consumer 판정을 사용한다.
- pose/joints가 만료되면 C3에 위임된 현재 로봇 표시를 숨긴다. 위험은 UNKNOWN과
  원인을 표시하며 collision envelope도 제거한다. 기존 목표/초기 자세 URDF에는 손대지 않았다.
- path/costmap/source는 각자의 기존 TTL을 따른다. source evidence kind는 원본 그대로다.
  LIVE 출처라도 paused/invalid이면 현재 관측을 보장하지 않는다고 표시한다.
- 수신 즉시 메타데이터만 검사하는 `offer`가 원래 local receipt, source age/expiry,
  순서와 C1 invalidation을 보존한다. 대기 1개, geometry cache와 asset cache는 유지한다.
  step/resume 때 TTL을 다시 시작하지 않는다. 같은 source stamp의 반복 HTTP 응답도 같다.
- 이전 응답이 더 최신의 대기 패킷을 덮지 못한다. paused 상태의 C1 만료 통지도
  이미 표시된 frame을 즉시 무효화하며, 뒤늦은 ready 응답으로 복구되지 않는다.
  map revision/source epoch/stream reconnect/clock 변경은 기존 context guard로 차단한다.
  이전 context의 대기도 비운다. 내부 arrival token은 원본 packet에 묶이고 한 번만 소비한다.
- C1 원본 timestamp, decimal ns, host receipt, TTL, validity interval, clock/epoch 정책은
  변경하지 않았다. **`c1_adapter.js`, `c1_assets.js`는 변경 없음**. 0.1/0.2 모두 유지한다.
  pose/joints/collision geometry 부재는 unavailable이며 새 관측을 합성하지 않는다.

## 실제 전후 결과

C5 `2a51d990…`의 HANDOFF, `peer_review.mjs`, `peer-review.json`을 읽기 전용으로
읽고 같은 `multi → 표시 일시정지 → 실제 2600ms` 절차를 재현했다.
C5 helper를 주입하거나 수정하지 않았다. 별도 실제 C3 consumer와 실제 DOM/renderer를
동시에 검사했다. 최초 재현은 기준 HEAD의 feature/consumer 그대로다.

| 엔진 | 수정 전 | 수정 후 |
|---|---|---|
| Chromium 151.0.7922.34 | consumer STALE; 화면 FRESH/CAUTION, robot=true | consumer·화면 STALE, UNKNOWN, robot=false |
| WebKit 26.5 | consumer STALE; 화면 FRESH/CAUTION, robot=true | consumer·화면 STALE, UNKNOWN, robot=false |

[수정 전 데이터](evidence/paused-freshness/before.json),
[수정 후 22개 회귀 및 실측](evidence/paused-freshness/paused-browser.json).
같은 390×1000 viewport의 [Chromium 전](evidence/paused-freshness/chromium-before.png) /
[후](evidence/paused-freshness/chromium-after.png),
[WebKit 전](evidence/paused-freshness/webkit-before.png) /
[후](evidence/paused-freshness/webkit-after.png).
일시정지 해제·새 정상 패킷으로 fresh 표시가 복구됨도 확인했다.

## 정확한 의존성과 실행 경계

| 역할 | 고정 SHA | 이번 사용 |
|---|---|---|
| C1 | `50600c7bce6f5fae743cd836ca1d8ee68d91b05a` | 실제 0.2 validator/clock normalizer/service/authenticated loopback HTTP/assets/저장; 실행 blob은 이전 C1 pin과 동일 |
| C4 | `7ac0d55b07abd20902d6d756c6b225733613fea7` | canonical ports·인계·composition 증거 읽기만; runtime/ROS 실행 NOT_RUN |
| C5 | `2a51d9906c39bd332191ce4c570b4152f13c2676` | 실패 절차·증거 읽기만; helper 실행/수정 없음 |
| D1 | `203c144f6b4a90966839c34b603ae12ee676cb12` | 실제 seeded solve → C1 save/reload, 합성 800점/preview 160점 |
| D2 | `7313f0a31c00ae87ae216b84ca41a23804e91917` | 실제 process_lidar / tracker, 합성 입력 |
| D3 | `356d0a036eb62d546e159e12a0691d7f5ea278f6` | 실제 assess / canonical_assessment, 합성 clock·coverage |
| C2 | `47a1d031d797c098c38a0147894523d07d30db8f` | 기존 동결 pin의 20개 단기 C1 호환성 후 동결 유지; 실제 저장용 host를 읽기 전용 재사용 |

C1/D1/D2/D3/C2 host 각 12/6/4/7/1 Git blob을 실행 전 검증했고 export는 쓰기 불가다.
공용 PCD/SE3 5개씩도 C1/D1/D2 SHA와 동일하다. [파일별 manifest](evidence/paused-freshness/manifest.json).
다른 역할 소스를 merge/cherry-pick하거나 C3에 복제·게시하지 않았다.
C4 인계의 과거 `C1_VERSION_UNSUPPORTED`는 C3 `a2b6d37…`에 대한 기록이며 이번
C3 0.2 검사와 구분한다. C4 command assessment를 실측 pose/joints로 가장하지 않는다.

[실제 core 보고서](evidence/paused-freshness/core-results.json)의 입력은 SYNTHETIC이다.
D1 정합·저장 후 D2→D3→C1 순서로 실행했다. 실측 sensor/clock/coverage 검증이 아니다.
Native는 이전 실제 원격 run **40840774827**, SHA
`fa8e26e02194d3c99ccc7b8e45eb3177a6fce19d`, artifact **12882393645**의 기록 재생이다.
ZIP SHA256 `0f09cf101555dbef3368fc6913acd9cdd61e380ad45c51472ea5e6b1b3cdc6aa`를 검증했다.
원래 plan/costmap·시간을 실제 C1 HTTP로 소비하며 없는 joints/assessment는 unavailable이다.
**로컬 ROS/native 실행·실장비 접속·TF/명령·배포·실이동은 NOT_RUN.**

## 검증 집계

| 검사 | PASS / FAIL / SKIP |
|---|---|
| C3 unit | **51 / 0 / 0**: 기존 38 + 새 13; deterministic consumer/contract, asset transport fault는 mock |
| 새 pause 실제 browser | **22 / 0 / 0**: 11 조건 × Chromium/WebKit; 실측 관측 2건은 테스트 수에 중복 계산하지 않음 |
| 실제 C1 HTTP browser | **18 / 0 / 0**: 엔진별 6 cases + paused expiry + frozen source + native record replay |
| 기존 C3 fixture browser | **11 / 0 / 0**, 1200 packets≥10Hz, pending≤1/history≤3 및 기존 메모리 기준 유지 |
| 동결 C2 호환성 | **20 / 0 / 0**: ports는 mock, DTO는 실제 현재 C1 validator |
| 공용 Python | **3115 / 0 / 2**, 3117 run; C3 unit은 wrapper 1개 안에 포함 |
| 공용 JS | **699 / 0 / 0** |
| JS syntax / Ruff / mypy / secret / whitespace | **117 modules / PASS / 4 files PASS / PASS / PASS** |

Python optional skip은 SVG plotting(matplotlib)·rosbags 각 1개이며 이번 변경으로 추가하지
않았다. Python 3.12.3 / Node 24.22.1 / Playwright 1.62.1. 무거운 검사는 직렬 실행했다.
로컬 테스트 로그와 실제 초기 DOM/consumer, paused DOM/consumer, HTTP bytes/hash를
[증거 디렉터리](evidence/paused-freshness)에 분리 보관한다.

초기 실패도 보존한다. 기존 fixture test는 이제 즉시 거절된 패킷에 Step을 누르려다
비활성 버튼에서 timeout이었다([초기 결과](evidence/paused-freshness/fixture-initial.json)).
거절을 늦추거나 timeout을 늘리지 않고 빈 큐/비활성 Step을 직접 확인하도록 바꿨다.
WebKit 최초 launch의 Chromium 전용 인수 오류는 엔진별 옵션으로 수정했다.
WebKit HTTP 첫 검사에서는 250ms 원래 validity를 넘긴 266ms에 fresh를 요구하여
정확히 EXPIRED로 실패했다([초기 결과](evidence/paused-freshness/actual-webkit-timing-initial.json)).
최초 완료된 DOM render를 MutationObserver로 즉시 기록해 같은 시점의 consumer와
비교하고, 실제 2600ms pause 만료를 별도로 확인하도록 고쳤다. 원래 source clock,
TTL, assertion, timeout과 skip 기준은 완화하지 않았다. WebKit의 부족한 라이브러리는
/tmp에 추출·연결했고 시스템 패키지/프로젝트 의존성은 변경하지 않았다.
최종 파일 해시 대조에서 이전 C2 임시 export가 지정 pin과 다른 것을 발견했다.
정확한 `47a1d031…`을 새 읽기 전용 export로 만든 후 20개를 다시 실행했다.
이전 export의 PASS는 최종 C2 근거에서 제외했다.
원본 생성 지도·PCD·압축 costmap은 게시하지 않고 증거 JSON에는 해당 배열의
개수/hash만 남겼다. 원본 로컬 보고서 hash는 manifest에 별도로 기록한다.

## 변경 파일, 재현, 제출 및 남은 연결

- 제품 후보: `obstacle_scene/index.js`, `consumer.js` 두 파일만.
- 검사: `tests/expansion_c3/{test_consumer,test_canonical,browser,actual_browser,paused_browser}.mjs`.
- 전용 실험: `prepare_dependencies.py` C1 pin 및 README 명령.
- C3 문서: 이 보고서, INTEGRATION_POINTS, HANDOFF/ROUND2_V02 최신 안내와 작은 증거.

[실행 명령](../../../experiments/expansion_20261029/c3_scene_ui/README.md),
[제품 hook](INTEGRATION_POINTS.md). 실제 테스트한 source SHA256은 manifest에 있다.
최종 제출 SHA는 이 문서를 추가한 커밋
`git log -1 --format=%H -- docs/parallel-expansion-20261029/C3/PAUSED_FRESHNESS.md`로
확정한다. 해당 HEAD를 기존 C3 브랜치에만 push하고 원격 일치 및 **그 HEAD의 최종 CI**를
최종 응답으로 보고한다. 커밋 전 이 문서에서 아직 실행되지 않은 원격 CI를 PASS로
선언하지 않는다. 공용 CI는 peer/native export를 fetch하지 않으므로 위 실제 연결 검사의
대체 증거가 아니다. main/공용 앱/운영 URDF/goal heading/ROS/Nav2/CI 파일은 변경하지 않았다.

**남은 제품 연결 한 가지:** 승인된 공용 scene host에서 생산자 소유 canonical 관측 feed와
전용 current-robot 표시 포트를 연결하기. 그 입력에는 실측 clock/mount/calibration 및
motion-volume coverage가 포함되어야 한다. 이번 수정은 독립 모듈의 표시 유효성까지이며
제품 연결·새 D3 보호 활성화·실로봇 회피 성공을 의미하지 않는다.
