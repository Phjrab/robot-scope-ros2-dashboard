# 실행 결과 — 2026-11-11

## 소스와 환경

- 인수/첫 진행률 재현 소스: `4b244d4024327c070482cdd71f4732ea081962d7`. 게시 후보 `090afc7ecc24cd0db49374fa4865084bd52cb45d`에서도 같은 재현을 재실행했고 결과/production 파일 hash가 일치했다.
- Ubuntu CI 인수: [42991493271](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/42991493271), failure. Ubuntu 22.04/Python 3.10 browser shard 2에서 **168 passed / 1 failed**.
- 실패는 `old active bridge explains missing inhibit capability and sends no implicit commands`, `toBeDisabled`의 실제 값 enabled. 과거 UNKNOWN/OCCUPIED 실패를 현재 실패로 복사하지 않았다.
- 별도 I0 인수 CI [42991493081](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/42991493081)는 success. A3/native 증거가 아니다.
- 로컬: Debian 13.6 x86_64, Python 3.12.14, Node 24.22.1, Playwright 1.62.1 Chromium. Python venv와 npm/browser 캐시는 `/workspace/work/` 아래에 설치했다. ROS/rclpy 없음; 장비 접속/VPN/비밀 바인딩 없음.
- 로컬 수정본 시험은 위 HEAD + 이번 diff로 수행했다. 게시한 exact commit과 그 CI는 [HANDOFF.md](HANDOFF.md)에 기록한다. 아래 소스 파일 hash 및 재현 JSON은 revision을 보완한다.

설치된 주요 의존성: fastapi 0.162.4, pydantic 2.14.3, numpy 1.26.4, scipy 1.11.4, PyYAML 6.0.1, Pillow 12.3.0, opencv-python-headless 4.10.0.84, uvicorn 0.54.0, websockets 15.0.1. Chromium 151.0.7922.34 (revision 1234).

## 관측 버튼: 재현과 원인 분리

1. 변경 전 원본 테스트 `--grep 'old active bridge' --repeat-each=12`: **12 passed**. 단독 반복으로 CI 실패가 항상 생기지는 않았다.
2. fixture의 post-pair preparation GET을 snapshot 생성 후 보류했다. blocker를 `CONTROL_BRIDGE_INHIBIT_UNSUPPORTED`로 바꾸고 `refresh(true)`를 호출한 후 구 응답을 해제했다. 제품 수정 전 **1 failed**, 동일한 enabled/disabled assertion 실패.
3. 제품에는 이미 `blockers.length > 0`에 따른 렌더 및 클릭 guard가 있었다. `refreshing` 중 강제 refresh가 즉시 반환하여 최신 조회를 버리는 것이 재현된 경로다. 실제 CI의 내부 scheduling 자체를 trace로 완전히 입증한 것은 아니다.
4. 수정: 강제 요청을 합쳐 후속 GET으로 처리하고 그 완료까지 동일 Promise로 기다린다. 새 요청이 예약되면 구 응답/오류를 적용하지 않는다. 조회 중 시작 버튼과 handler를 닫고, 기존 exact-session 종료는 계속 허용한다. 종료 중 겹친 읽기 뒤에도 새 상태를 조회한다.
5. 수정 직후 원본+고정 재현 반복: **12 passed**. 추가 회귀는 blocked/unblocked/최신 read 실패, 복수 강제 요청 병합, handler 직접 호출에도 POST 없음, 늦은 응답 중 exact-session stop을 검사한다. assertion·timeout·품질/소유권 기준은 줄이거나 늘리지 않았다.
6. 실제 FastAPI 라우터 + `FastlioObservationSession` + 서명 transport/bridge core 시험: admission 직전 capability 제거 후 **409**, `control_bridge_inhibit_unsupported`; service dispatch·bridge 전송·센서 source 변경 0. 모의 systemd/메모리 링크이며 실제 ROS/하드웨어가 아니다. `test_fastlio_observation.py`: **15 passed**.

## 실행 명령과 최종 결과

공통 작업 디렉터리 `/workspace/work/robot-scope-ros2-dashboard`; Python 명령은 `/workspace/work/venv/bin`을 PATH 앞에 둔다. 브라우저 명령은 `PLAYWRIGHT_BROWSERS_PATH=/workspace/work/browsers`를 사용한다.

| 명령 | 실제 결과 |
|---|---|
| `npm ci --ignore-scripts` (workspace cache), `npx playwright install chromium` | 설치 완료. 최초 기본 npm cache는 home 쓰기 실패였으며 설치/시험 통과로 세지 않음 |
| `python3 -m unittest discover -s tests -p 'test_fastlio_observation.py' -v` | 15 passed |
| `npx playwright test tests/e2e/navigation_preparation.spec.mjs tests/e2e/pre_nav_draft.spec.mjs --reporter=line` | 106 passed (종료 겹침 회귀 추가 전). UNKNOWN/OCCUPIED 포함 |
| 최종 준비/초안/운영 주행/health/event safety/goal URDF/preset/goal precision 브라우저 8파일 | **127 passed**, 4.2분 |
| `python3 -m unittest discover -s tests -v` (첫 환경) | 3,741 run, failures 6, skips 35. **통과 아님** |
| 아래 회수 실행기에서 `python3 -m unittest test_mapping_jobs test_slam_broker -v` (`PYTHONPATH=tests`) | 57 passed |
| 아래 회수 실행기에서 `python3 -m unittest discover -s tests -v` (`C2_CROSS_REQUIRED=1`) | **3,741 run / 3,706 passed / 35 skipped / failures 0**, 200.208초 |
| `node --test tests/*.mjs` | 765 passed, 0 skipped |
| `node scripts/check_frontend_syntax.mjs` | 135 modules passed |
| `python3 -m ruff check robot_dashboard scripts` | passed |
| `python3 -m mypy --config-file mypy.ini` | passed, configured 4 source files |
| `python3 scripts/check_repository_secrets.py`, `git diff --check` | passed (게시 전 재확인) |

최종 브라우저 명령:

```sh
npx playwright test tests/e2e/navigation_preparation.spec.mjs tests/e2e/pre_nav_draft.spec.mjs tests/e2e/operational_navigation.spec.mjs tests/e2e/navigation_health.spec.mjs tests/e2e/navigation_event_safety.spec.mjs tests/e2e/navigation_goal_urdf.spec.mjs tests/e2e/navigation_presets.spec.mjs tests/e2e/goal_precision.spec.mjs --reporter=line --output=/workspace/work/navigation-final
```

첫 Python 실패의 환경 원인: 컨테이너 PID 1은 `tail -f /dev/null`로 고아 자식을 회수하지 않아 프로세스 종료 검사 5개가 zombie PID를 계속 보았다. 기본 umask `0077`은 `mkdir(mode=0755)` fixture를 0700으로 만들어 unsafe parent 거절 검사 1개를 실패시켰다. 테스트/제품은 수정하지 않고 Linux subreaper와 umask 022에서 재검증했다. 회수기는 이 테스트의 자식만 회수하며 기존 PID 1이나 시스템 프로세스를 변경하지 않는다.

실행한 `/workspace/work/run_with_reaper.py`의 내용:

```python
import ctypes, os, subprocess, sys
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
    raise OSError(ctypes.get_errno(), "PR_SET_CHILD_SUBREAPER failed")
os.umask(0o022)
child = subprocess.Popen(sys.argv[1:])
while True:
    pid, status = os.waitpid(-1, 0)
    if pid == child.pid:
        child.returncode = os.waitstatus_to_exitcode(status)
        raise SystemExit(child.returncode)
```

```sh
C2_CROSS_REQUIRED=1 python3 /workspace/work/run_with_reaper.py python3 -m unittest discover -s tests -v
```

## 진행률 위험: 실패를 숨기지 않는 별도 실행

```sh
python3 scripts/reproduce_navigation_progress.py
```

**exit 1 / REPRODUCED / controls_ok=true**. exit 1을 통과로 집계하지 않는다. [PROGRESS_REPRODUCTION.json](PROGRESS_REPRODUCTION.json)에 exact SHA, production callback/classifier 파일 hash, 모든 결과를 저장했다.
거리 순서는 현장 기록의 rounded 값이고 시각은 합성이다. 실제 gateway callback/health를 호출했으며 표시 백분율은 현재 UI 공식의 계산값이다. 실제 브라우저/ROS bag replay나 물리 이동 증거는 아니다.

| 대조 | 결과 |
|---|---|
| `.0416856 → .838 → .681 → .581 → .531 → .515 → .490` | initial=.042, 표시 계산 0%, rate=0, DEGRADED/GOAL_PROGRESS_TOO_LOW |
| 작은 첫 값 없는 정상 접근 | initial=.838, 약 41.53%, rate=.02778m/s, READY/HEALTHY |
| 실제 정체 대조 / zero-only / ±.002 noise / 후퇴 | 모두 DEGRADED/GOAL_PROGRESS_TOO_LOW, 기존 제한 유지 |
| 취소 중 feedback | 진행 상태 변경 없음 |
| 실제 send_goal 초기화 / 이전 goal callback | baseline reset 확인 / 이전 세대 거절 |
| 새 goal 정상 feedback | READY, 약 18.74% |
| 새 gateway 재시작 후 작은 첫 양수 | 동일 0% 결함 재현 |

최초 진단 실행은 restart fixture를 pending에 둬 health가 READY였고 종합 결과 NOT_REPRODUCED였다. 합성 goal acceptance를 실제 response callback으로 전달한 뒤 위 결과가 나왔다. 첫 시도를 최신 재현 결과로 오기하지 않는다.

수정 검토: callback의 goal generation/ID는 이미 검증되므로 예전 goal callback 차단만으로 해결되지 않는다. 현재 `/plan` 관측은 선택적 metrology이며 feedback에는 소비한 path ID/stamp가 없다. 첫 거리 증가만 보고 reset하거나 선택적 `/plan` 수신만으로 feedback을 신뢰하는 수정은 채택하지 않았다. 새 goal에 속하는 plan/feedback 연결 및 초기 baseline 확정 근거를 별도로 검증해야 한다. native stall timeout·STOP/lease/watchdog·Safe mode·품질 기준·지도·교정·프리셋은 변경하지 않았다.

이번 native ROS/Nav2, 장비 정지/이동 시험은 모두 NOT_RUN이다. 전체 suite의 A3/확장 관련 소프트웨어 검사나 과거 native CI를 운영 저장지도 위치추정 전체 통과로 계산하지 않는다.

최종 Python skip 사유(통과에서 제외):

- 3건: `C1 exact-SHA dependency export not supplied`
- 1건: `NOT_RUN: ROS Humble/native Nav2 1.1.20 not installed; no DDS init`
- 1건: `NOT_RUN: ROS bridge exact SHA core dependencies required`
- 1건: `NOT_RUN: current exact SHA read-only owner exports required`
- 16건: `NOT_RUN: exact SHA read-only C1/D2/D3 exports required`
- 7건: `exact C1/C4 exports required: run round2_check`
- 1건: `exact round2 C1 export not supplied`
- 1건: `explicit exact owner exports required; no automatic fetch`
- 2건: `explicit pinned owner export required; mock tests are separate`
- 1건: `optional SVG plotting dependency absent`
- 1건: `optional rosbags backend not installed`

## 게시 코드 exact-SHA CI

코드 `090afc7ecc24cd0db49374fa4865084bd52cb45d`의 [CI 42996364533](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/42996364533)는 **success / 7 jobs success**다. Ubuntu 22.04/Python 3.10, Ubuntu 24.04/Python 3.12의 Python 전체/JavaScript/정적·의존성/API fixture와 네 browser shard가 모두 성공했다. 별도 [I0 42996364303](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/42996364303)도 **success**다. 2026-11-11 18:46:56 KST 확인. 이들은 하드웨어 없는 검증이며 native/장비 통과가 아니다.


## 후속 2회차 — 새로운 Ubuntu 환경에서 재검증

인수 SHA `488d279b3a97300db80fd32843008b3e83344c5a` + 이번 진단/검사 diff.
production gateway, health classifier, app.js, preparation.js 변경 없음.
작업 디렉터리 `/home/desktop1/Documents/ChatGPT/robot/robot-scope-ros2-dashboard`.
Ubuntu 24.04.5 x86_64, Python 3.12.3, Node 24.22.1, Playwright 1.62.1,
Chromium 151.0.7922.34 (1234). ROS/rclpy 없음. venv는 `/tmp/nav-validation-venv`.
requirements.txt/requirements-competition-offline.txt/requirements-quality.txt로 설치했고
pip check 통과. numpy 1.26.4/scipy 1.11.4/PyYAML 6.0.1/Pillow 12.3.0/
fastapi 0.162.4/pydantic 2.14.3을 사용했다.
CI와 같은 고정 C2 비교 커밋 765622e/380800c/9e9ebcc를 fetch했다.

### 첫 실패와 환경 조정 (통과에 포함하지 않음)

1. 최초 재현은 pydantic 부재로 import 실패. sandbox pip도 DNS 제한으로 실패했다.
   임시 venv에 필요한 의존성을 정상 네트워크 환경에서 설치한 뒤 원본 재현을 실행했다.
2. sandbox 전체 unittest는 첫 비동기 시험에서 진행하지 않아 중단(exit 130).
   별도 socket 생성 probe가 EPERM을 확인했다. 완료된 전체 suite 결과가 아니다.
3. sandbox Node는 85개 파일 단위 종료만 보고했다. 이를 765개 assertion 통과로 쓰지 않고
   정상 프로세스 환경에서 Node 24로 실행해 765 passed / 0 skipped를 확인했다.
4. 첫 완료 Python 전체: 3,746 run / failures 1 / errors 1 / skipped 35, **실패**.
   `expansion_c3.test_module`은 기본 Node 18.19.1의 ESM 해석 실패;
   `test_https_listener...off_partial_origin_bind_and_key_guards`는 umask 0002에서
   openssl이 생성한 cert의 group-write 권한 때문에 기존 보안 검사에서 거절됐다.
   Node 24 PATH + umask 022에서 두 모듈 4 tests passed. 제품/검사 완화 없음.
   PID 1/subreaper 문제를 가정하지 않았고, 이번에는 subreaper를 쓰지 않았다.
5. 시스템 npm 부재로 첫 npm ci는 시작하지 못했다. bundled pnpm으로 `/tmp`에 npm 10을
   준비하고 원래 package-lock 그대로 npm ci --ignore-scripts를 완료했다.
   Chromium 다운로드는 완료됐으나 FFmpeg 다운로드가 ENETUNREACH로 지연되어 중단했다.
   video=off인 기존 검사에 설치된 full Chromium(channel=chromium)을 사용했다.
   timeout/assertion/worker를 늘리거나 줄이지 않았다.

### 실제 명령

```sh
# 아래 PATH를 로컬 검사에 적용; 기존 기본 Node 18과 구분한다.
export PATH=/tmp/nav-validation-venv/bin:/home/desktop1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH
umask 022
C2_CROSS_REQUIRED=1 python3 -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
python3 -m ruff check robot_dashboard scripts
python3 -m mypy --config-file mypy.ini
python3 scripts/check_repository_secrets.py
python3 -m pip check
git diff --check
```

브라우저 명령은 이전 8파일을 그대로 사용했다. `/tmp/nav-playwright.config.mjs`는
기존 playwright.config.mjs를 import하고 testDir/webServer.cwd를 절대경로로 지정하며
use.channel만 chromium으로 지정했다. 나머지 기존 timeout/worker/expect 설정 유지.

```sh
PLAYWRIGHT_BROWSERS_PATH=/tmp/nav-browsers node node_modules/playwright/cli.js test --config=/tmp/nav-playwright.config.mjs tests/e2e/navigation_preparation.spec.mjs tests/e2e/pre_nav_draft.spec.mjs tests/e2e/operational_navigation.spec.mjs tests/e2e/navigation_health.spec.mjs tests/e2e/navigation_event_safety.spec.mjs tests/e2e/navigation_goal_urdf.spec.mjs tests/e2e/navigation_presets.spec.mjs tests/e2e/goal_precision.spec.mjs --reporter=line --output=/tmp/nav-browser-final
```

**127 passed (2.8m)**. UNKNOWN/OCCUPIED와 강제 refresh·unsupported 관측·exact stop
회귀를 포함한다. 실제 로봇/ROS 연결은 아니다.
JS **765 passed**, JS syntax **135 modules**, Ruff/mypy(4 source files)/pip check/diff 통과.
새 진단 검사 **5 passed**. source secret scan은 staging 후에도 다시 수행한다.

### 진행률 별도 진단

`python3 scripts/reproduce_navigation_progress.py`:
원본과 확장본 모두 **exit 1 / REPRODUCED / controls_ok=true**.
확장본 세 재현(기존/재시작/수락 goal+matching plan) 모두 initial=.042m,
remaining=.490m, 표시 공식 0%, rate=0, DEGRADED/GOAL_PROGRESS_TOO_LOW.
[후속 JSON](FOLLOWUP_2_PROGRESS_REPRODUCTION.json)은 인수 HEAD + 진단 diff 실행이며
각 실행 파일의 SHA256을 포함한다. 아직 게시된 exact commit 실행으로 해석하지 않는다.
별도 정상 짧은 목표·큰 왕복·generation/ID 분리·부분 재현/대조 실패 판정 검사를 추가했다.
임시 메모리 mutant(증가 때 baseline reset)는 왕복 검사 1건에서 실패하여 거절했다.
이 의도된 mutant 실패와 재현 exit 1은 정상 회귀 통과 수에 포함하지 않는다.


### 후속 최종 로컬 결과

Node 24 PATH + umask 022, C2_CROSS_REQUIRED=1 전체 재검사:
**3,746 run / 3,711 passed / 35 skipped / failures 0 / errors 0**, 150.213초.
35 skip의 사유/개수는 위 최초 회차의 최종 skip 목록과 같으며 통과에서 제외했다.
로컬 원본 로그는 `/tmp/nav-python-corrected.log`, `/tmp/nav-js-unsandboxed.log`,
`/tmp/nav-browser-final.log`; 실패 로그는 `/tmp/nav-python-final.log`와 구분한다.
운영 소스 파일들은 기준 SHA와 동일하며, 새 A3/native 통과를 주장하지 않는다.


### a3f50c7 exact-SHA 게시 후 검사와 새 I0 실패

`a3f50c7f448c06140f51a9c31f447f2975db0395`을 정상 push했고 ls-remote main이 일치했다.
clean exact SHA에서 재현을 재실행: **exit 1 / REPRODUCED / controls_ok=true**.
[exact-SHA JSON](FOLLOWUP_2_EXACT_SHA_PROGRESS.json)의 실행 파일 hash와 case 결과는
커밋 전 확장본과 일치한다. 검증용 source archive의 **2,726 파일**을 Git blob과
전체 대조했다. [archive 영수증](FOLLOWUP_2_ARCHIVE_RECEIPT.json). 장비 배포 후보가 아니다.

새 I0 [43005433124 attempt 1](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43005433124/attempts/1)은 **failure**.
C0 component PASS 후 full-app의 `explicit_confirm_then_stop_real_receipt`에서
`proposal_cleanup.state === SETTLED && proposal_display_valid === true`의
expect.poll이 기존 5초 안에 true를 관측하지 못했다. 확인 checkbox 조작 전 실패로
confirmation DOM observation은 NOT_STARTED다. 이후 I0 단계는 skipped이며 통과가 아니다.
[첫 실패 요약·hash](FOLLOWUP_2_I0_FIRST_FAILURE.json); 원본 artifact 13847977450을 보존했다.

서버 응답은 ready/MONITORING 뒤 ready/SETTLED, pose age 약 .025~.029초를 포함한다.
실패 후 DOM은 제안 freshness 만료를 표시한다. 실패 당시 렌더 내부 상태·poll별 관측이
없으므로 scheduling/제품 경합/fixture의 구체 원인을 확정하지 않았다.
제안 poll 2초와 유효 창 1초는 기존 구현이며 이번에 변경하지 않았다.

동일 clean SHA의 로컬 명령:
`PLAYWRIGHT_BROWSERS_PATH=/tmp/nav-browsers python3 scripts/check_c0_prior_integration.py --output /tmp/nav-c0-repro-1`
(Node 24와 venv PATH, umask 022). **component PASS / full-app PASS**,
전체 source hash 불변·소유 fixture server 종료 확인. 이 통과가 원격 첫 실패를 취소하지 않는다.
재현 여부를 보기 위해 실패 job을 동일 SHA에서 **한 번만** 재실행했다.
어떤 재실행 결과도 원인 수정 증거로 쓰지 않으며 assertion/timeout은 그대로다.


### I0 재실행 결과와 probe 관측 수정

`a3f50c7` 일반 CI [43005433103](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43005433103)은
**success / 7 jobs success**. I0 [attempt 2](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43005433124/attempts/2)는
**같은 assertion에서 failure**다. [두 번째 실패 영수증](FOLLOWUP_2_I0_SECOND_FAILURE.json).
추가 rerun은 하지 않았다. I0 전체를 통과로 표시하지 않는다.

CPU 4배 합성 지연과 읽기 전용 MutationObserver를 넣은 임시 probe도 로컬 full-app PASS였다.
이 임시 계측은 `/tmp/nav-full-app-observed.mjs`/`/tmp/nav-check-c0-observed.py`에만 있고
제품 코드나 실제 환경 성능 증거가 아니다. CI 원인은 여전히 완전히 계측되지 않았다.

다만 같은 predicate와 기존 5초 제한에서 기본 expect.poll이 유효 창을 놓치는 경로를
고정된 합성 DOM에서 재현했다. 1950~2750ms, 3950~4750ms만 SETTLED/valid=true로
렌더했으나 실제 poll은 약 16/119/372/875/1878/2880/3883/4887ms에 false만 읽고 실패했다.
[실제 표본](FOLLOWUP_2_POLL_ALIAS_REPRODUCTION.json). 이는 CI 타이밍의 원시 replay가 아니다.

`tests/fixtures/planar_prior_integration/readiness_wait.mjs`는 동일한
`cleanup.state === SETTLED && proposal_display_valid === true`를 브라우저의 RAF로
관측한다. 제한은 **5000ms 그대로**이고 서버 조회·명령·신선도 연장·제품 timer 변경은 없다.
full_app_probe의 해당 대기만 이 helper로 바꿨으며 나머지 확인·exact stop·INITIAL POSE·match
assertion을 유지했다. 정상 짧은 유효 창, 두 조건의 동시 충족, SETTLED여도 stale이면
기존 제한 내 실패하는 브라우저 회귀 3건을 추가했다.

수정 후 로컬 `check_c0_prior_integration.py --output /tmp/nav-c0-probe-final`:
**component PASS / full-app PASS / 전체 source 불변 / 소유 fixture server 정상 종료**.
이번 수정은 검증 probe가 실제 렌더된 상태를 놓치는 경로의 수정이며, 운영 위치추정
소비/장비 정합/진행률 계산이 수정됐다는 뜻이 아니다.


최종 probe 수정본 로컬 결과: Python **3,746 run / 3,711 passed / 35 skipped**,
153.940초, failures/errors 0. JavaScript **765 passed**. 기존 8파일 + 새 probe 파일의
브라우저 **130 passed**. C0 component/full-app 각각 PASS 및 소유 server 종료 확인.
Ruff/mypy/diff 재확인 통과. 기존 1초 freshness와 검사 5초 제한, 운영 source는 그대로다.
이 결과는 a3f50c7 + probe/문서 diff이며 후속 게시 commit의 CI와 구분한다.
