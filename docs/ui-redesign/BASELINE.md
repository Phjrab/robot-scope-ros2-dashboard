# Baseline

- HEAD: `92194cad2f2f91add260791f2e73f86db6bcbd20`, main에서 clean 시작.
- branch: `codex/ui-robot-scope-mission-control`.
- npm lifecycle는 테스트 스크립트뿐. `npm ci --offline --ignore-scripts`로 lockfile 그대로 4 packages 설치; 새 dependency 없음.
- API startup 대신 `scripts/ui_fixture_server.mjs`가 127.0.0.1:4187에서 static assets만 제공. API/WebSocket은 Playwright의 in-memory fixture로 처리. 다른 hostname 요청은 차단.
- 격리 브라우저 최초 실행은 sandbox loopback `EPERM`; 승인된 범위에서 loopback 실행 권한을 받아 Chromium 재실행 성공.
- `npm run test:unit`: 334 PASS, 0 fail (`evidence/baseline-unit.txt`).
- `python3 -m unittest discover -s tests -p 'test_final_architecture.py' -v`: 5 PASS.
- 전체 Python baseline: 1441 tests, errors 6, skip 1. 기존 환경에 fastapi/pydantic이 없고 offline registration subprocess가 실패했다 (`evidence/baseline-python.txt`). 최종 validation에서 복구 결과와 비교한다.
- 실제 route baseline 캡처: `captures/before/*.png`, 동일 fixture/scenario/viewport를 manifest에 기록. 1440×900 및 1366×768의 Observation/Navigation/Maps/Capture/Disconnected; tablet/mobile Observation/Disconnected.

화면 관찰: 248px sidebar, 큰 제목/설명 공간, 녹색 장식/큰 radius, cockpit 안전·panel label이 6~10px. 1440×900에서 장면은 있지만 inspector와 카메라가 기본 관측 흐름에 없다. 작은 viewport에서 길어진 shell이 장면보다 앞선다.
