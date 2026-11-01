# I0 검증 기록과 재현

최종 machine-readable 기록은 [RESULTS.json](RESULTS.json), 정확한 upstream CI는 [SOURCE_CI.json](SOURCE_CI.json), 코어 용량 집계는 [CAPACITY_RESULTS.json](CAPACITY_RESULTS.json)이다. 각 결과는 아래 계층을 구분한다. 새 native/실장비 실행을 했다는 주장은 없다.

## 기준 main과 최종 회귀

| 검사 | 시작 main | I0 통합 |
|---|---|---|
| Python 전체 unittest | 3132, OK, skip2 | 3370, OK, skip35; 원본의 명시 dependency/native skip 보존 |
| JS | root 77파일 PASS | root+확장 84파일: 776검사 중774 PASS, 원본 historical export2 skip |
| frontend syntax | 112모듈 PASS | 129모듈 PASS |
| Ruff / 지정 mypy | PASS / 4파일 PASS | PASS / 4파일 PASS |
| 기존 전체 브라우저 | 227 PASS | 227 PASS, 원래 timeout/assertion 유지 |
| mission actual-API fixture | 별도 baseline 미실행 | 10 PASS |
| 설치된 실제 I0 integration | 없음 | 18 PASS: 지도·권한·default OFF·실제 runtime·replay |
| I0 제품 브라우저 | 없음 | 9 PASS: 2/3/누적 지도, 6개 viewport/theme, C4→C1→C3, 로컬 replay |
| 과거 native 기록 | 원격 원본 근거만 | hash 검증5개 parser PASS, 제품 재생1개 PASS; native 새 실행 아님 |
| 선택 HTTP dependency 제거 | 없음 | httpx/httpx2 import 강제 차단 상태에서 API4개+C7 실제 HTTP PASS |

로컬: Python3.12.3, Node20.20.2, Playwright1.62.1/Chromium151.0.7922.34. CI는 실제 설치 dependency와 Ubuntu22.04/Python3.10 및 Ubuntu24.04/Python3.12를 별도 확인한다. 로컬 최초 시스템 Node18은 ESM 자동 판별이 없어 기존 main JS부터 실패했다. 검증은 기존 CI와 같은 Node20으로 수행했으며 생산 코드의 module format을 바꾸지 않았다.

skip35는 ROS native1, 선택 plotting1, rosbags1 및 원본의 별도 exact-export 조건32개다. 이 skip을 통합 PASS로 세지 않는다. 대신 설치 모듈 대상18개, 제품 HTTP/브라우저, C7의 독립 exact-SHA export CLI를 명시 실행했다. 원본 historical export를 최신 SHA라고 속이거나 skip/timeout을 바꾸지 않았다. JS의 별도 historical C1 fixture2개도 skip으로 남기고 현재 실제 C1/D1 경로는 제품 시험으로 검증했다.

## 실제 실패와 수정

- C2 preview/job 비교가 JSON 객체의 key 삽입 순서에 의존했다. 객체 순서만 무시하고 모든 key/value/type·배열 순서를 보존하는 재귀 비교로 수정했다. reorder·extra field·type·배열 불일치 회귀를 추가했다. 실제 2/3/누적 저장과 ancestry409가 통과했다.
- C6 슬라이더 input 처리에서 pause callback이 UI 값을 이전 playhead로 되돌린 뒤 seek 값을 읽었다. 먼저 사용자가 선택한 시각을 캡처하도록 수정했다. public DOM의 실제 slider와 native 기록 재생에서 검증했다.
- C6 원본 데모 CSS는 전역 selector와 고정 dark 색을 사용했다. 제품에서는 독립 scoped replay.css와 기존 theme token을 사용한다. 밝은 테마 설명문 대비4.5이상, 가로 overflow 없음, 44px/키보드를 검사하고 실제 PNG를 확인했다.
- 기존 shared fixture의 socket onClose만으로는 context 종료 시 interval이 해제되지 않았다. 3회 종료에서 잔류1→2→3, 추가 callback2→5→8을 재현했다. page/context close에도 idempotent 정리를 연결한 뒤 각각0/0이다. reconnect timeout과 pose callback도 해제한다. TIMER_BEFORE/AFTER.json 참조. 이 결과가 과거 CI의 모든 timeout 원인을 해결했다는 뜻은 아니다.
- 신규 app hook의 최초 배치가 app.py line-cap 검사를 초과해 bootstrap으로 분리했다. 기존 no-store 계약 검사도 그대로 통과하도록 응답 header 소유를 app entrypoint에 유지했다.
- 역사적 C7 결과 JSON을 인수하지 않아 report 재생 단위 검사가 실패했다. 비공개 environment/path를 제거한 allowlist 테스트 fixture를 추가했다. 과거 보고서를 새로운 측정값으로 제시하지 않는다.
- 첫 I0 CI b899f746dff27d4d1825f02fc15ea00fab7d92cd는 신규 테스트의 선택 TestClient/httpx2 의존 때문에 실패했다. C1의 기존 stdlib+uvicorn 실제 HTTP transport로 바꾸고, C7도 optional HTTP dependency 없이 loopback을 사용한다. 같은 테스트 수·assertion·timeout을 유지했다. 원격 실패 run은 41272699684 및 41272699859다.
- sandbox에서 socket/subprocess/async queue가 제한되어 일부 실행이 실패했다. 동일 한도를 유지한 승인된 호스트 loopback에서 재검증했다. 운영 network/ROS에는 연결하지 않았다.

## 남겨둔 기존 결함과 native 차단

POLL_BEFORE_HOST.json: 기존 global_observation_contract.js가 poll 진입 시 changed 통지를 하지 않아 화면의 이전 활성 버튼을 누르면 openHistorical가 조용히 return한다. 재시도하면 원래404 오류가 표시된다. I0는 이 생산 파일을 수정하지 않았다. 후속 수정은 reading 상태 통지, accepted open intent 직렬화, map/source/generation/active-owner 재검증과 결정적 delayed-status 회귀가 필요하다. 전체227 PASS와 별개로 재현되는 결함이다.

로컬 ros2/rclpy/opt/ros 없음. DDS init·native 재실행0. C4 인계의 OWNER_SOURCE_IDENTITY_UNAVAILABLE / GRAPH_ENDPOINT_CONTRACT_UNAVAILABLE, QoS UNKNOWN/history0는 통과시키지 않았다. C4 native→Nav2 marking/clearing/plan/actuator는 BLOCKED_NATIVE_IDENTITY다. 과거 D3 native5개 성공은 별도 기준이며 C4 성공으로 세지 않는다.

## C7 결과 해석

wire 131072B, sample16384B, compact14336+reserve2048B 경계에서 exact limit까지 수용하고 +1을 거부했다. latest queue는60입력/58대체/2처리, executing1+pending1, close후 queue0/latest=null이다. source/map/clock fence, 전체 geometry와 full-source PCD 경계도 검증했다. threshold를 넓히지 않았다.

실행시간은 명시 구간의 perf_counter 값이다. 다른 로컬 프로세스 부하는 통제하지 않았으며 clock mapping 없는 sensor→render latency와 Jetson/실시간 적합성은 UNKNOWN/NOT_RUN이다. browser-load 부하는 별도 C3 fixture 근거이고 수치 코어→제품 end-to-end latency가 아니다.

## 재현 명령

Python3.12/Node20 및 requirements.txt, requirements-competition-offline.txt, requirements-quality.txt를 별도 환경에 설치한다. 저장소 밖 운영 환경을 변경하지 않는다.

```sh
python -m unittest discover -s tests -v
node --test tests/*.mjs tests/expansion_c2/*.test.mjs tests/expansion_c3/test_*.mjs tests/expansion_c6/test_replay.mjs
node scripts/check_frontend_syntax.mjs
python -m ruff check robot_dashboard scripts
python -m mypy --config-file mypy.ini
python scripts/check_repository_secrets.py
python -m tests.integration_i0.verify_declared_dependencies
npx playwright test
npx playwright test --config playwright.competition.config.mjs
npx playwright test --config playwright.i0.config.mjs
```

C7은 SOURCE_LOCK/PINS의 Git 객체를 먼저 확보한 clone에서 실행한다. prepare는 source를 read-only로 export하고 전후 blob을 검증한다.

```sh
python -m robot_dashboard.expansion_diagnostics prepare --repo . --output /tmp/i0-pinned
OPENBLAS_NUM_THREADS=1 python -m robot_dashboard.expansion_diagnostics run --deps /tmp/i0-pinned --profile baseline --output /tmp/i0-baseline.json
OPENBLAS_NUM_THREADS=1 python -m robot_dashboard.expansion_diagnostics run --deps /tmp/i0-pinned --profile bounded --config-snapshot /tmp/i0-baseline.json --output /tmp/i0-bounded.json
python -m robot_dashboard.expansion_diagnostics summarize /tmp/i0-bounded.json --output /tmp/i0-summary.md
```

C6 로컬 기록은 manifest와 원본을 사설 디렉터리에 보관한 뒤 `python -m robot_dashboard.run_review --root <private-dir> --manifest <manifest.json> --installed-contracts --output <new-private-output>`로 변환한다. review.private.json만 picker로 읽으며 공개 저장소에 넣지 않는다.

과거 D3 ZIP은 SOURCE_LOCK의 SHA256와 source-sha를 `python -m tests.expansion_c6.prepare_native <archive> <new-private-dir>`로 검증한다. 5개 fixed scenario만 추출한다. 변환한 empty 기록은 `I0_NATIVE_REVIEW=<review.private.json> npx playwright test --config playwright.i0-native.config.mjs`로 별도 제품 재생 검증한다. 이 명령은 ROS를 실행하지 않는다.

## CI 읽기

기존 CI trigger/job은 수정하지 않았다. I0 branch 전용 offline product workflow를 추가했고 production deployment는 없다. 최종 HEAD별 상태는 다음 명령의 모든 run/job을 확인한다. 문서 commit 자체의 CI는 그 commit 이후 발생하므로 해당 snapshot 시각과 최종 채팅 보고를 구분한다.

```sh
gh api 'repos/Phjrab/robot-scope-ros2-dashboard/actions/runs?head_sha=<40-char-I0-HEAD>'
gh api 'repos/Phjrab/robot-scope-ros2-dashboard/actions/runs/<run-id>/jobs'
```
