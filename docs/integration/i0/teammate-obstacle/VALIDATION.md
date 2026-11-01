# 비이동 검증

기준 완료 SHA `cdf9e04e3da6478409c19c2be3e1e35a58b229be`, 체크포인트 커밋 `595c32176143504b8c7ed472645e1e1a8cac1c2d`, 최종 검증 코드 SHA `c9567302dc519920bb7a094aea25a0fb35a55c5b`. 이후 문서 커밋은 코드 변경이 없다. 원본 팀원 base846121b의 결과와 I0 후속 결과를 합산하지 않는다.

변경 전 재실행: Python3370(35 skip), JS776(774 pass/2 skip), main browser227 PASS. [BASELINE.json](BASELINE.json) 참조. 최초 수용표는 [T3_FIRST_PASS.json](T3_FIRST_PASS.json)으로 먼저 저장했다. Python25/26·JS63/64, cone browser11·기존 제품9·syntax131·Ruff PASS였고 독립 검사를 멈추지 않았다.

실패를 구분했다.

1. 초기 신규 테스트2개: 미지원 `follow_redirects` 옵션과 C1 adapter의 선행 차단을 고려하지 않은 JS 기대. 기존 stdlib HTTP client를 유지하며 redirect handler를 테스트 안에 설치했고, JS는 adapter의 일관성 차단과 consumer의 LIVE 승격 거부를 각각 검증했다.
2. 첫 전수 Python3396: 기존 clock-unknown 테스트1개와 no-store 검사1개 실패. 새 정책은 populated source epoch의 clock 교체를 거부하므로 기존 테스트에 명시 reset과 거부 assertion을 추가했다. reset 뒤에도 unknown clock의 unavailable/age null 검사를 유지한다. C1 snapshot의 실제 no-store 누락은 router에서 수정했다. 테스트 삭제/timeout 증가/한도 완화는 하지 않았다.
3. 시각 QA: 밝은 UI에서도 renderer canvas는 어두워 글자가 어두웠다. cone 글자를 밝게 하고390px에서는 ID만 캔버스에 표시하며 치수는 inspector에 유지했다. scoped checkbox 폭과 줄바꿈을 보완했다. 수정 뒤8개 폭/테마 화면을 재검증했다.
4. timer probe 첫 실행은 Playwright 경로 환경 누락으로 launch하지 못했다. 기존 설치 경로를 명시해 재실행, 세 round 모두 잔여 interval/종료 후 callback0. 제품 결함으로 분류하지 않았다.

| 수용 항목 | 결과·근거 |
|---|---|
| 관련 flag OFF / cone toggle OFF | 기존 설치 boundary PASS, 원 index/API/worker 그대로; cone glyph0/추가 cone API0 |
| source 미설정 / 권한 | C1 503/401, absent legacy404, mutation405 PASS; bounded backoff1–30초 |
| 합성 입력 / frame / 치수 | committed scenario→실제 C1→실제 C3→기존 renderer; 5개, radius .1/height .25, SIMULATED PASS |
| frame 이름 / map revision·generation·source epoch / source identity·space | ingress 또는 C3에서 거부/기존 geometry 제거 PASS |
| XY / 실제 z·자세 미확인 | flat-only 전용 공간, HEIGHT_UNVERIFIED·collision UNKNOWN PASS; 실측3D BLOCKED |
| duplicate / 역행 / restart | 같은 stamp에 sequence/receipt가 새로 와도 C1거부·C3 TTL 보존; source reset 필요 PASS |
| concurrent ingest | validation을 제어해12 commit 뒤11 도착시11 거부, 최종12 보존 PASS |
| 요청 pending / body stall / 늦은 응답 | C3 독립 만료, 3초 abort, dispose 후 callback·reschedule0 PASS |
| server age + transport + local elapsed | 800+100+101ms가1초 TTL 초과 시STALE, 동일 stamp anchor 보존 PASS |
| empty vs stale empty | VALID 0개 → STALE, WAITING으로 숨기지 않음 PASS |
| invalid / oversized / duplicate keys | 전체 거부, last-good receipt 보존, max64/C1 snapshot128KiB PASS |
| pause / resume / tab / unmount / reopen | TTL계속 경과, overlay1→0→1, 기본 toggle OFF, listener/timer/abort unit PASS |
| 390/820/1280/1440 dark/light |8개 실제 Canvas·DOM smoke, 상태행 contrast≥4.5, 가로 넘침 없음 PASS |
| C0 / Goal / Initial / 기존 대시보드 | 관련 공유 파일 후속 diff0; 전체 browser/mission 회귀, C0 결합 자체 NOT_RUN |
| 제어면 | 브라우저 관측/표시 중 write0·외부 요청0, 제어 owner 없음·collision UNKNOWN; DEVICE_NOT_RUN |
| 실제 cone node / map calibration / Jetson | PAIRED_REAL_PRODUCER_INPUT_REQUIRED / UNALIGNED / HEIGHT_UNVERIFIED / NOT_RUN |

최종 집계와 log SHA256는 RESULTS.json에 기록한다. skipped 항목은 기존35개 Python(원본 export gates/ROS native/optional SVG/rosbags), JS2개 historical export fixture다. 새 cone 테스트 skip은0이다. mypy는 기존 설정4개 파일 검사이며 새 adapter를 strict type-check했다고 주장하지 않는다. Ruff는 robot_dashboard/scripts와 새 demo/tests도 통과했다.

재현(기존 requirements, Python3.12, Node20, Chromium 설치 필요):

```bash
OPENBLAS_NUM_THREADS=1 python3 -m unittest discover -s tests -v
node --test tests/*.mjs tests/expansion_c2/*.test.mjs tests/expansion_c3/test_*.mjs tests/expansion_c6/test_replay.mjs
python -m unittest discover -s tests/integration_i0 -t . -v
python -m tests.integration_i0.verify_declared_dependencies
node scripts/check_frontend_syntax.mjs
python -m ruff check robot_dashboard scripts
python -m mypy --config-file mypy.ini
python scripts/check_repository_secrets.py
npx playwright test --reporter=line
npx playwright test --config playwright.competition.config.mjs --reporter=line
npx playwright test --config playwright.i0.config.mjs --reporter=line
npx playwright test --config playwright.i0-cones.config.mjs --reporter=line
node experiments/expansion_20261030/c7_capacity/ci/socket_cleanup_probe.mjs .
```

원래 CI workflow는 변경하지 않았다. I0 offline workflow에 cone browser11 + transport5를 추가했으며 synthetic screenshot/trace만 artifact로 보존한다. 최종 문서 HEAD의 CI는 그 HEAD를 push한 뒤 실행되므로 자기 자신의 SHA/완료 상태를 이 파일에 미리 기록할 수 없다. 정확한 최종 HEAD의 두 workflow/네 job terminal 상태는 최종 채팅에 별도 보고한다. 조회 시40자리 SHA를 사용한다.

```bash
gh api 'repos/Phjrab/robot-scope-ros2-dashboard/actions/runs?head_sha=<40-character-final-HEAD>&per_page=20'
gh api repos/Phjrab/robot-scope-ros2-dashboard/actions/runs/<run-id>/jobs
```

원본 팀원이 보고한 live_observation:753 단발 실패를 기존 flaky라고 단정하지 않았다. 이번 변경 전/후 전체 suite 결과를 분리해 남겼다. 기존 I0의 Maps history poll/open 경합은 별도 알려진 미해결이며 이번에도 수정하지 않았다. 실장비·ROS native·지도 정합 연구·C0 실행 환경은 검사 대상이 아니다.
