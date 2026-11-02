# C0 → main 통합 보고 — 2026-11-02

현재 단계: **CANDIDATE_LINUX_CI_PENDING**. 독립 clone의 로컬 main에서 부모 관계를 보존한 통합 후보를 준비했다. 원격 main 반영과 exact-main CI는 아직 미완료이며, 아래 소스별 과거 성공을 통합 성공으로 대체하지 않는다.

## 소스와 보존

병합 전 main `31ebb43ef7196bba7eced45ed37854eabc5e2927`, C0 `cc7e0fc526eb2fec365f1df84d1dd5f422da83d1`, 공통 조상 `846121b4988ed2932d329020857925558f8f2c79`를 원격에서 다시 확인했다. 고유 커밋은 main 17개/C0 63개다. I0 기준 `ae41a9b6cf5cf5c7c133e818e3fad4693eb2053e`는 이미 main의 조상이므로 다시 병합하지 않았다. 최신 AGENTS의 main 직접 commit/push 정책과 main 보호 규칙 없음, push hook 없음, hosted CI만 실행되는 workflow를 확인했다.

`archive/20261102/pre-c0-main-31ebb43ef719`, `archive/20261102/c0-merge-source-cc7e0fc526eb`를 새 annotated tag로 게시하고 원격 peeled SHA를 각각 확인했다. C0 원본 브랜치를 이동하거나 삭제하지 않았다. 기존 clone/worktree·미커밋 파일·사적 증거는 변경하지 않았다. 태그는 tracked Git 보존이며 장비·미추적 데이터 백업을 대신하지 않는다.

## 충돌 해결과 최소 변경

일반 3-way `merge --no-ff --no-commit`을 사용했다. 공통 조상 대비 main 변경 322경로, C0 변경 176경로의 교집합 및 실제 충돌은 `tests/e2e/dashboard_backend.mjs`, `tests/e2e/live_observation.spec.mjs` 두 파일이다. 파일 전체 덮어쓰기·ours/theirs 일괄 선택·squash/rebase는 사용하지 않았다.

- 소켓별 공용 `onFixtureSocketClose`를 page/context/socket/명시 dispose의 단일 idempotent 정리 경로로 결합했다. 정리 후 양쪽 listener를 해제하고 interval/reconnect timeout과 등록 집합을 한 번만 제거한다. main의 `backend.dispose` 및 context 종료 보장, C0의 정확한 close 횟수·listener 정리·새 준비 API fixture 응답을 모두 보존했다.
- lifecycle 회귀에 context 종료·명시 dispose·중복 종료 검사를 추가했다. 관련 53개 검사와 실제 Chromium context 종료 3회에서 잔여 interval/종료 후 callback 0을 확인했다.
- Linux 전용 `/proc` 계약을 바꾸지 않고 기존 C0 실제 ASGI/전체 앱 하니스를 실행하는 `scripts/check_c0_prior_integration.py`를 추가했다. 전체 source hash 고정·전후 대조, grouped contract, 별도 증거 디렉터리, 소유한 loopback 서버 종료를 강제한다. fixture에는 초기화 전 읽기 전용 source identity 경로만 추가했다. 기존 I0 CI에 이 검사와 artifact를 추가했으며 기존 모든 검사·trigger·한도는 유지했다.

제품 코드 추가 수정은 **0**이다. main 변경 제품 파일 102개와 C0 변경 제품 파일 38개가 각 고정 부모와 바이트 일치한다. 인수 제외·비활성화 경로는 없다. 전체 파일 목록·변형·subtree hash는 [SOURCE_LOCK](SOURCE_LOCK.json)에 있다.

I0 `/extensions`, 지도 job/전체 사본 저장·재조회, C1/C3 renderer/TTL/source stamp, C5 scoped UI, C6 REPLAY, C7 CLI와 기존 콘 통합을 보존했다. 확장 flag·CONES는 기본 OFF, `BLOCKED_AUTH`, `BLOCKED_NATIVE_IDENTITY`, `ADVISORY_ONLY`, 합성 콘 표시 한계를 유지한다.

C0 지도 조합/계보·복사형 변환·선택/교정, X/Y/yaw 미전송 초안, 조건부 proof/그룹 all-member, capture-time source/session/generation·TTL, exact-stop receipt·서명·STOP/lease·Nav2 handoff, 명시 INITIAL POSE와 별도 match, null/`—`와 실제 0, 초기 점/방향과 실제 추정/목표 URDF를 인수했다. 불확실 반경·각도 필수 입력을 되살리지 않았고 서버 정책 0.25m/0.20rad와 별도 handoff 한도도 바꾸지 않았다. 후방·측면 후보의 `ALL_DIRECTION_BASELINE`/`NOT_ADOPTED` 상태를 유지한다.

## 로컬 검증과 첫 실패 보존

로컬 환경은 macOS arm64, Python 3.12.16, Node 26.13.0, Playwright 1.62.1이다. CI의 고정 offline/quality 의존성을 원본 변경 없이 기존 wheel cache에서 설치했다. 최초 PyPI 접속 timeout은 환경 실패다. 아래 숫자는 서로 다른 실행 단위이며 합산하지 않는다.

| 검사 | 결과·범위 |
|---|---|
| `python3 -m unittest discover -s tests -v` | 3,683 run; 8 failure entries / 59 errors / 37 SKIP. macOS 전체 PASS로 표시하지 않음. Linux CI 필요 |
| `node --test tests/*.mjs` | 750 PASS |
| expansion C2/C3/C6 JS (I0 workflow와 동일 glob) | 82 PASS / 2 기존 historical SKIP |
| C0 helper `test_contract_assertions.mjs` | 10 PASS |
| `python -m unittest discover -s tests/integration_i0 -t . -v` | 45 PASS |
| `python -m tests.integration_i0.verify_declared_dependencies` | PASS: optional httpx/httpx2 차단, 실제 I0/C7 HTTP |
| Ruff, 설정 mypy, frontend syntax, secrets, pip check, diff check | PASS; mypy 4파일, JS syntax 133모듈 |
| 기존 전체 `npx playwright test` | 327 PASS / 6 FAIL. 6건 모두 준비 API subprocess가 system Python의 fastapi를 못 찾음. 경로 수정 후 해당 6건 별도 실행 PASS; 전체 333 PASS로 재표기하지 않음 |
| 실제 app import + loopback HTTP | OFF 4 GET / ON 6 GET PASS. 기존 ROS import stub, production lifespan OFF. 루트/자산 no-store, OFF 404·ON BLOCKED_AUTH, C0 미설정503와 optional bounds/exact-stop/STOP/Cancel OpenAPI 확인. POST/센서/제어 실행0 |
| shared fixture timer / runner 경계 | 실제 browser context3회 잔여0·늦은 callback0; runner 경계11 PASS |

전수 Python의 오류59개와 실패5개는 Linux `/proc/<pid>/stat` 부재에 연결된다. 제품 identity를 임의 값으로 대체하지 않았다. Hesai 실패2개는 fake ros2 shebang에 공백 포함 Python 경로가 들어간 환경 문제이며 동일 소스·공백 없는 interpreter의 두 검사에서 PASS했다. SLAM overlay 실패1개는 관련 제품/테스트가 양쪽 부모와 동일하고 과거 I0에서도 관측됐다. 분리 실행도 실패했고 진단 실행만 통과했으므로 원인은 미확정이며 수정 완료/단순 flaky로 표시하지 않는다. Linux exact-candidate CI로 지원 환경의 결과를 별도 확인한다.

초기 소규모 Python 호출의 잘못된 test 이름/import 경로, 확장 JS의 `python` PATH 부재, 첫 Chromium 권한 오류와 private app-smoke의 FastAPI 내부 router 열거 문제도 환경/검사 도구 실패로 보존했다. 소스 assertion·timeout·TTL·안전 조건을 낮추지 않았다. source manifest 2,650경로가 로컬 검사 전후 같았고 이후 변경은 CI runner/fixture identity/workflow 및 인계 문서뿐이다.

추가 mission browser 10개와 콘 browser 11개는 PASS했다. I0 제품 첫 실행과 startup 진단 실행은 server startup 10초 timeout으로 각각 테스트0개 실행이며, 원인 진단을 별도로 진행한다. 시간/검사 조건을 늘리지 않았다. Linux 후보 CI 결과는 완료 후 이 보고서에 확정한다. Linux C0 하니스는 실제 준비/proposal/confirmation/stop/match API와 UI를 사용하지만 센서·solver·Nav2/ROS는 합성이다. MATCH_ARMED는 요청 경로 성공이지 연속 정합·실장비 위치 정확도·주행 준비가 아니다.

## 첫 Linux 후보와 실행기 보완

첫 부모보존 merge 후보는 `0947497db7f004ce0c2b47e2848cbaecdd6ef674`, 보존 태그는 `archive/20261102/c0-main-candidate-0947497db7f0`다. 첫 [I0 CI 41415084487](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41415084487)는 새 C0 helper 단계에서 5 PASS/5 FAIL로 종료됐다. helper의 과거 ungrouped proof fixture에 실행기가 `PRIOR_REQUIRE_GROUPING=1`을 잘못 주입한 원인이 확인됐다. 실제 ASGI/전체 앱 및 후속 I0 검사는 이 실행에서 SKIP이며 성공으로 표시하지 않는다. 실패 run/artifact는 보존하고 자동 재실행하지 않았다.

실행기만 보완하여 legacy unit fixture는 기존 모드로 실행하고, 실제 component/full-app에는 그룹 검증을 계속 필수 적용한다. 별도 중단 반례에서 최상위 명령은 실패하지만 개별 receipt가 PASS로 남는 문제도 발견해, probe 완료 전 중단은 receipt에도 FAIL로 기록한다. 해당 회귀 2개(중단 위치/예외 종류 4개 조합 포함)와 helper10개가 통과했다. 제품 및 원래 검증 assertion/한도는 변경하지 않았다. 수정 후보는 별도 commit/tag로 검증한다.

## 게시·인계 경계

후보의 Linux 표준 CI와 I0 통합 CI를 확인한 뒤 main에 정상 forward push한다. push 직전 원격 ref를 다시 대조하며 force push하지 않는다. 최종 main SHA와 그 exact-SHA 두 CI의 run/job/step 결과는 게시 후 최종 receipt로 확정한다. 자신의 최종 SHA를 문서에 넣기 위한 commit 반복은 하지 않는다.

단일 최신 현장 인계는 [A0_HANDOFF](A0_HANDOFF.md)다. 기존 I0 인계는 이 문서로 안내하되 과거 기록을 보존했다. A0는 C0/I0를 다시 병합하지 않고 통합 main에서 검증을 시작한다. 현재 장비 readback/배포·복구, 정지 관측·초기값, exact stop/인계·Nav2·INITIAL POSE·정합, 지속 TF/odom, 별도 승인 P1/P2·stop-and-go·경사로와 독립 I0 의존 항목은 NOT_RUN이다. 기존 Maps history poll/open 경합은 미수리 backlog로 남는다.

**DEVICE_NOT_RUN**: 로봇/Jetson 접속·배포·서비스 재시작·센서·실제 ROS graph/TF/INITIAL POSE/goal/속도·자세 명령·주행 모두0. 새 알고리즘·지도 정합 연구를 시작하지 않았다.
