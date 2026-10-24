# C1 review — 브라우저 CI 복구와 공용 연결 준비

## A. 기준과 범위

- 역할: C1. 제출 브랜치: `review/20261024-c1-ci-integration`.
- 실제 작업 기준: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`.
- 작업 시작 및 브랜치 전환 시 확인한 원격 main: 동일한 `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`.
- 독립 일반 clone에서 시작했다. 다른 채팅의 checkout/index/branch를 변경하지 않았다.
- C1 변경을 main에 commit/push한 이력은 없다. 사용자의 제출 방식 변경에 따라 작업을 보존하여 지정 브랜치로 전환했다. AGENTS.md는 수정하지 않았다.
- 테스트 대상 소스 커밋: `a49a89b067cdf28678d619ec7ff0a3122de5105c`. 아래 검사는 이 커밋에 기록된 최종 소스 내용을 대상으로 수행했다. 최종 제출 HEAD는 검토 문서를 추가한 후의 별도 커밋이며 마지막 응답에서 보고한다.

| 종류 | 경로 | 실제 변경 |
| --- | --- | --- |
| 추가 | `robot_dashboard/static/features/package.json` | 기존 ES module feature 코드에 `type: module` 명시 |
| 수정 | `tests/e2e/competition_mission.spec.mjs` | 명시적 waypoint 좌표 입력 → 실제 로컬 API 저장 → GET 비교 → 브라우저 draft 삭제 후 재조회 검사 |
| 수정 | `tests/e2e/ui_redesign_fixture.mjs` | 누락된 FAST-LIO read-only 비활성 상태 fixture 추가 |
| 수정 | `.github/workflows/ci.yml` | 기존 전체 E2E 유지, 실제 미션 API fixture E2E 추가, 실패 시 브라우저 증거 artifact 업로드 |
| 수정 | `playwright.config.mjs` | 실패 screenshot 보존; 기존 retain-on-failure trace 유지 |
| 추가 | `docs/mission-competition/c1/INTEGRATION_POINTS.md` | canonical DTO/락/goal/ACK/시간/카메라/STOP 통합 지점과 default-off 설계 |
| 추가 | `docs/parallel-review/20261024/C1/REVIEW.md` | 이 검토 문서 |

삭제·이동 파일 없음. 학습 가중치/사용자 RGB/PCD/map/환경/캐시/대형 실행 결과를 포함하지 않는다. C2/C3/C4/D0 소스와 공용 DTO/API/runtime binding은 변경하지 않았다.

## B. 문제와 구현

### 원본 CI 로그와 전달 문서의 차이

[실패 run 40075428356](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40075428356)의 실제 원본 job 로그를 GitHub API로 확인했다. 두 matrix 모두 Node **20.20.2**에서 다음 오류로 Playwright 수집이 중단됐다.

```text
SyntaxError: Named export 'GO2_JOINT_NAMES' not found.
The requested module '../../robot_dashboard/static/features/maps/observed_joints.js'
is a CommonJS module ...
```

- [Ubuntu 22.04 / Python 3.10 원본 job](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40075428356/job/120817622150)
- [Ubuntu 24.04 / Python 3.12 원본 job](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40075428356/job/120817622345)

해당 job의 실제 Python 결과는 2,691 tests, JS는 660 tests다. 전달 문서의 `Mission dialog opens with explicit waypoint input`, `tests/browser_smoke.spec.mjs`, `#mission-create-button`/`#mission-dialog`, 2,738/656 집계는 이 고정 커밋/원본 job의 내용과 일치하지 않는다. 해당 파일/선택자도 checkout에 없다. 이 설명을 실제 수정 원인으로 사용하지 않았다. GitHub CLI의 `run view --log`가 빈 결과를 반환하여 `gh api .../actions/jobs/{job_id}/logs`로 원본을 조회했다.

로컬 Node 24에서는 수집이 성공했지만 정확한 CI 버전 Node 20.20.2로는 같은 오류와 0개 수집을 재현했다. Node 바이너리는 공식 배포 SHASUMS256과 일치 확인했다. 수집 전 실패이므로 baseline 브라우저 screenshot/trace는 생성되지 않았다; 존재하지 않는 화면 증거를 만들지 않았다.

ES 모듈 feature 폴더에만 형식을 명시하여 CI Node 20에서도 191개 전체 E2E를 수집한다. [Node package type 규칙](https://nodejs.org/api/packages.html#type)을 따른다. 상위 static 폴더에는 `navigation.js`, `control_input.js` 등의 CommonJS/UMD 유틸리티가 있어 전체 static을 module로 전환하면 안 된다. 작업 중 발견한 이 범위 문제를 수정해 기존 JS 660개 회귀를 모두 보존했다. root package와 의존성 lockfile은 그대로다.

### 수집 복구 후 발견한 fixture 누락

전체 191개 브라우저 검사에서 187개가 통과하고 UI consistency 4개가 `/api/v1/observations/fastlio` GET 404로 실패했다. 실제 router와 `FastlioObservationSession.snapshot()`을 대조한 뒤 shared UI fixture에 `UNAVAILABLE`, `can_start=false`, `can_stop=false`, `observation_only=true` 응답을 추가했다. 해당 fixture는 GET만 허용한다. 오류를 무시하는 allowlist나 assertion 완화는 추가하지 않았다. 실패 screenshot/HTML context/trace로 실제 화면과 요청 오류를 확인했다.

### 미션 작성 검증 의도 보존

기존 HANDOFF와 현재 `initializeMissionPage`에 따르면 기본 UI는 지도 기반 경로·미션 workspace이며 기존 주석 미션 편집기는 고급 메뉴에 있다. 가짜 dialog나 대체 UI를 추가하지 않았다.

새 E2E는 지도 위에 방문을 만든 뒤 x=1.5m, y=2.25m, yaw=90°를 명시적으로 입력한다. 실제 Python router/service/PlanStore의 POST 201 응답과 GET 정의를 비교하고, localStorage를 삭제한 뒤 reload하여 서버 저장 내용과 좌표가 복원되는지 확인한다. 실행 이력은 비어 있고 legacy mission/goal mutation은 없음을 확인한다. 기존 대회 DRAFT, native 차단, server timer/재접속, mobile/theme/STOP fixture 검사 4개도 유지한다.

`tests/competition_fixture_server.py`는 private TemporaryDirectory와 명시적 fake navigation을 사용한다. production `app.py`를 import하지 않으며 goal/cancel 메서드는 AssertionError로 거부한다. 실제 장비 endpoint는 사용하지 않는다.

### 공용 연결 준비

정확한 경로와 메서드는 [INTEGRATION_POINTS.md](../../../mission-competition/c1/INTEGRATION_POINTS.md)에 있다. 주요 검토 지점:

- `MissionRoutes`의 request ledger/CAS, `_admission`, preflight와 기존 `MissionCoordinator`/`NavigationCoordinator` shared lock 유지.
- navigation의 lowercase goal state, 정확한 goal ID, terminal cancellation 확인과 물리 STOP/HOLD ACK를 별도 취급.
- `Evidence`의 epoch/sequence/config/owner/run/step/goal/generation과 source clock 의미 보존. receiver TTL 0.25초와 fixture evidence gap 0.5초를 혼동하지 않음.
- C4는 기존 CameraHub가 공급한 snapshot을 받는 경계만 사용하도록 설계. replay가 camera ownership이나 synchronized capture를 증명하지 않음.
- 각 action capability는 계속 `UNCONNECTED`, `native_enabled=false`. fixture executor는 그대로이며 runtime/native 등록 코드는 추가하지 않음.

## C. 검증

환경: 로컬 Ubuntu 24.04.5 x86_64 / Python 3.12.3 / Node 20.20.2 / Playwright 1.62.1 / Chromium 151.0.7922.34. Python은 C1 전용 `.venv`에 기존 프로젝트 테스트 의존성 사본을 넣고 `pip check`로 확인했다. 호스트 전역 패키지/OS/서비스는 변경하지 않았다. localhost fixture와 Chromium/asyncio가 필요한 검사는 sandbox 밖 로컬 테스트 권한으로 실행했다.

| 검사 | 실제 결과 |
| --- | --- |
| 고정 기준 Node 20 Playwright 수집 | FAIL 재현: GO2_JOINT_NAMES CommonJS 오류, 0 tests |
| 최종 Node 20 Playwright 수집 | PASS: 191 tests / 27 files |
| 전체 Python unittest | PASS 2,689 / SKIP 2 / FAIL 0, 총 2,691 |
| 전체 JavaScript unit | PASS 660 / FAIL 0 |
| 전체 기존 browser E2E (수집 오류 수정 후) | 187 PASS / 4 FAIL: 누락된 FAST-LIO fixture |
| 최종 fixture 수정 후 관측/UI consistency 재검사 | PASS 18 / FAIL 0; 최종 snapshot 필드값 확인 후 실패 사례 4개 재검사도 PASS |
| 실제 미션 API fixture E2E | PASS 5 / FAIL 0 |
| Ruff / mypy | PASS / PASS (mypy configured 4 files) |
| JS syntax | PASS 104 modules |
| tracked-source secret scan / diff whitespace | PASS / PASS |
| canonical definition/evidence JSON schema 비교 | PASS, 현재 Pydantic schema와 동일 |
| pip check / npm audit | PASS / PASS (0 vulnerabilities) |
| 로컬 Python dependency vulnerability audit 및 coverage report | NOT_RUN; 기존 workflow가 원격 matrix에서 실행 |
| 로컬 Ubuntu 22.04 / Python 3.10 | NOT_RUN; 이 호스트는 Ubuntu 24.04/Python 3.12 |
| native Nav2 / 실제 모델·RGB replay / 실제 로봇 | NOT_RUN: C1 범위 밖 |

Python skip: optional SVG plotting dependency absent, optional rosbags backend not installed. 첫 sandbox JS 실행은 자식 runner 실패를 보였으며 정상 로컬 권한으로 재실행했다. 중간에 너무 넓은 module scope로 생긴 39개 JS 실패는 features 범위로 좁힌 후 모두 해결했다. 최종 통과 집계에 중간 실패를 합산하지 않는다.

재현 명령(저장소 root, 필요한 전용 Python/Node 환경 활성화):

```sh
node --version
node node_modules/@playwright/test/cli.js test --list
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
python3 -m ruff check robot_dashboard scripts
python3 -m mypy --config-file mypy.ini
python3 scripts/check_repository_secrets.py
node scripts/check_frontend_syntax.mjs
node node_modules/@playwright/test/cli.js test --reporter=line
node node_modules/@playwright/test/cli.js test --config playwright.competition.config.mjs --reporter=line
node node_modules/@playwright/test/cli.js test tests/e2e/ui_consistency.spec.mjs tests/e2e/live_observation.spec.mjs --reporter=line
python3 -m pip check
npm audit --audit-level=high
git diff --check
```

Playwright의 기본 static fixture는 127.0.0.1:4173/4174, real-API fixture는 127.0.0.1:4187이다. 다른 서버를 재사용/종료하지 않는다. 후자는 `COMPETITION_FIXTURE_PORT`로 전용 포트를 지정할 수 있다. baseline 재현은 변경 전 commit과 Node 20.20.2에서 `playwright test --list`를 실행한다. 테스트 결과 로그/4개 fixture PNG는 C1 로컬 work 폴더에만 있고 원격 업로드했다고 주장하지 않는다. 이번 workflow는 이후 실제 CI 실패가 생기면 해당 run의 browser-failure artifact를 보존한다.

최종 fixture 변경 뒤 전체 191개를 로컬에서 다시 일괄 실행하지는 않았다. 최초 187개 통과와 수정 후 영향 범위 18개/최종 4개 통과를 구분하며, 원격 matrix가 전체를 다시 검사한다. 원격 CI 상태는 push 뒤 실제 제출 커밋에 연결된 run을 조회하여 최종 응답에 별도 보고한다. 로컬 PASS를 원격 matrix PASS로 간주하지 않는다. 이 문서는 브라우저/합성/저장소 검증이며 실로봇 동작·물리 정지·카메라 시간 동기·지도 정합·온보드 성능을 증명하지 않는다.

## D. 의존성과 통합 참고

C1 CI 수정은 다른 역할의 결과 없이 독립 동작한다. 다른 역할 브랜치/커밋은 참고·병합하지 않았으며 branch 간 호환성은 NOT_RUN이다. 이후 필요한 것은 D0 실제 변경/해시, C2 실제 native adapter API, C4 실제 frame/replay API, C3 native 환경 증거다.

사용자의 명시적인 통합 승인 후 승인된 정확한 SHA만 별도 통합 브랜치에서 검토한다. 권장 검토 순서는 D0 provenance → C2/C4 소유권·시간·goal/ACK 연결 → C3 evidence 등록이다. 공용 wiring/service/capabilities/schema/UI가 예상 조정 지점이지만 현재는 수정하거나 활성화하지 않았다. 다른 역할이 요청한 공용 CI 변경도 승인 후 별도 비교가 필요하다.

롤백은 C1 커밋의 추가 package marker, E2E 검사, workflow/실패 증거 설정과 문서만 되돌리는 범위다. package marker를 제거하면 Node 20 수집 오류가 재발할 수 있다. mission 저장 포맷/지도/로봇 설정 migration은 없다. 공개 이력을 재작성하지 않는다.

유일한 workflow는 hosted Ubuntu의 hardware-free CI이며 branch push에 따른 장비 배포 작업은 없다. C1 지정 브랜치에만 push하고 PR/main 변경/자동 병합/다른 역할 통합/로봇 접속·배포·재시작·주행은 수행하지 않는다.
