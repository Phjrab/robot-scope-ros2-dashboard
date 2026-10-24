# C2 검토 제출 — native mission adapter

작성: 2026-10-24 KST. **구현·합성 검증 제출이며 검토 완료/통합 승인/실물 검증이 아니다.**

## A. 기준과 수정 범위

- 역할: C2. 브랜치: `review/20261024-c2-mission-adapter`.
- 실제 시작 기준: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`.
- 시작 시 remote main: 같은 `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`.
- 제출 전 확인한 remote main: `5d78fcb7c7589134a533d6dc0ddd09995f9163f9`.
- main 진행분: `ace55b0` 관측 UI polling/control 보완과 `5d78fcb` merge. 변경은 `docs/integration-acceptance/DASHBOARD_OBSERVATION_SESSION.md`, `robot_dashboard/static/features/maps/observation_session.js`, `tests/e2e/live_observation.spec.mjs` 세 파일이다. C2는 이 변경을 merge/cherry-pick/복사하지 않았고 원래 기준에서 진행했다.
- C2가 이미 main에 올린 변경: 없음. 다른 채팅의 checkout/index/branch를 변경하지 않았다.
- 구현 커밋 및 최종 Python 검증 대상: `9864f4d312b3c3b4adbff44d9c2eeeced9819cce`.
- 이 문서와 추가 검증 metadata를 포함한 최종 HEAD는 마지막 제출 응답에 별도 기록한다. 구현 SHA 이후에는 문서만 추가한다.

추가 파일 목록(기존 파일 수정·삭제·이동·바이너리 변경 없음):

```text
robot_dashboard/mission_routes/competition_native/__init__.py
robot_dashboard/mission_routes/competition_native/adapter.py
robot_dashboard/mission_routes/competition_native/authority.py
robot_dashboard/mission_routes/competition_native/contracts.py
robot_dashboard/mission_routes/competition_native/coordinator.py
robot_dashboard/mission_routes/competition_native/observations.py
robot_dashboard/mission_routes/competition_native/state.py
tests/competition_native/__init__.py
tests/competition_native/helpers.py
tests/competition_native/test_actions.py
tests/competition_native/test_authority.py
tests/competition_native/test_coordinator.py
tests/competition_native/test_observations.py
docs/mission-competition/native-adapter/HANDOFF.md
docs/mission-competition/native-adapter/WIRING_PROPOSAL.md
docs/mission-competition/native-adapter/INPUTS.json
docs/mission-competition/native-adapter/VALIDATION.json
docs/parallel-review/20261024/C2/REVIEW.md
```

기존 runtime 동작은 자동 변경되지 않는다. 새 패키지를 명시적으로 구성한 호출자는 fake port에서 신호/장애물/terrain/주차/OUT 행동 전이를 끝까지 검증할 수 있다. runtime 기본값은 비활성이고 공용 registry/API/schema/fixture/startup은 그대로다.

## B. 구현과 검토 지점

[설계·인계](../../../mission-competition/native-adapter/HANDOFF.md), [정확한 공용 연결 제안](../../../mission-competition/native-adapter/WIRING_PROPOSAL.md), [기준 입력 해시](../../../mission-competition/native-adapter/INPUTS.json)를 함께 검토한다.

| 주요 코드 | 변경된 동작 / 검토 초점 |
|---|---|
| `NativeActionAdapter` | 한 action의 호출 adapter. 명시 start, bounded request ledger, goal/constraint/cancel intent 소비, STOP 중 await 경합, cleanup 불확실성 보존. snapshot/import는 부수효과 없음 |
| `state.decide` | pure transition. 접근 종료/취소 ACK 후 HOLD, 두 발·STOP 연속 2초, fresh associated GREEN/pose/path, 새 exit generation, 실제 departure만 latch. 주차 5초·검증된 STAND, terrain 검증과 full OUT 분리 |
| `Normalizer` | canonical Evidence 재사용 + 내부 component sidecar. source/receiver age 분리, 검증된 clock 관계, scope/config/epoch/sequence/session fence, duplicate TTL 연장 금지, 같은 source stamp의 sequence 세탁 거부 |
| `CoordinatorNavigationPort` | 실제 coordinator start/resume/pause/snapshot 사용. 동일 admission/coordination lock, exact actual goal ownership, logical hex32 ID 변환. foreign/late cancel 거부 |
| `CommandBoundary` | 단일 최종 authority의 순수 참조: E-stop/충돌 > 모든 owner HOLD > terrain caps > tracking. fresh generation goal/command 없이는 RELEASE 후에도 0. 늦은 RELEASE가 최신 HOLD를 해제하지 못함 |

중요한 미연결과 회귀 위험:

1. **취소된 접근 leg 후 exit continuation**은 base coordinator에 native atomic hook이 없다. fake에서는 상태 전이·호출 순서가 구현됐지만 실제 bridge는 명시적 callback 없이는 거부한다. C1이 기존 owner lock 안에 추가해야 하며 원격 skip으로 대체하면 안 된다.
2. 성공한 접근 leg는 실제 after-arrival barrier/token으로 진행할 수 있다. C1의 내부 native barrier 컴파일과 UI/API 의미 분리가 필요하며 현 사용자 확인 경로를 native 자율 실행으로 오인하면 안 된다.
3. command reference는 실제 command consumer에 연결되어 있지 않다. Python HOLD 표시는 실제 actuator STOP 증명이 아니다. native 활성화 전에 watchdog/최종 authority ACK와 모든 command producer 경로를 검증해야 한다.
4. foot/body/physical stop/departure, clock calibration, signal association/model, posture/gait/terrain 검증 binding은 없다. `Activation`의 참조 문자열은 검증 절차를 대신하지 않는다.
5. source clock 관계와 age 계산은 trusted ingress가 책임진다. receiver session nonce도 ingress handshake로 바인딩해야 하며 과거 packet을 새 nonce/receipt로 세탁해서는 안 된다.
6. command TTL 0.25초와 synthetic evidence gap 0.5초는 다르다. native cadence는 미확정이며 별도 실측 policy를 넣지 않으면 start 불가다.
7. 내부 `ActionState/Packet/Extras`는 공용 enum/ROS message가 아니다. VM base에는 문서상의 개념 이름 대신 실제 `StopInput`이 있으므로 그 shape만 검증해 변환한다. canonical JSON schema는 변경하지 않는다.
8. timeout/watchdog tick은 기존 backend owner loop의 책임이다. 새 병렬 run engine/백그라운드 스케줄러를 만들지 않았다. 서버 재시작·재연결은 현재 action을 INTERRUPTED로 닫고 새 시도를 요구한다.

## C. 검증

환경: Linux x86_64, Python 3.12.3, Pydantic 2.13.4, Ruff 0.6.9, Node v24.19.0. 기존 프로젝트 가상환경을 사용했으며 전역 패키지는 바꾸지 않았다. Ruff는 기존 프로젝트 도구를 읽기 전용으로 재사용했다. CI의 Node 20/Python 3.10·3.12와 로컬 환경이 완전히 같지는 않다.

실제 명령과 결과는 [VALIDATION.json](../../../mission-competition/native-adapter/VALIDATION.json)에 기록한다. 아래 shell의 `python3`는 프로젝트 가상환경 Python, `node`는 번들 Node, Ruff는 고정 0.6.9 executable을 의미한다.

```bash
python3 -m unittest discover -s tests/competition_native -t tests -v
python3 -m unittest discover -s tests -v
ruff check --no-cache robot_dashboard scripts tests/competition_native
python3 -m mypy --config-file mypy.ini
python3 -m compileall -q robot_dashboard/mission_routes/competition_native tests/competition_native
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
python3 scripts/check_repository_secrets.py
git diff --cached --check
```

| 검사 | 결과 |
|---|---|
| C2 전용 unit/fake/실제 coordinator 계약 | **65 PASS** |
| 전체 Python | **2,756 실행 / 2,754 PASS / 2 SKIP / 실패 0**, 90.320초 |
| JavaScript | **660 PASS** |
| JavaScript syntax | **104 modules PASS** |
| Ruff 0.6.9 | **PASS**, robot_dashboard/scripts/C2 tests |
| mypy | **PASS**, 저장소 설정의 4개 소스 파일. C2 전체 타입 검증 주장이 아님 |
| compileall / tracked-source secret scan / diff whitespace | **PASS** |
| Browser E2E / ROS / native Nav2 / 실제 RGB·모델 / 실물 qualification | **NOT_RUN** |

Python SKIP 2건은 optional rosbags backend 미설치와 PCD_EDIT_NODE 미설정에 따른 기존 JS geometry parity 검사다. 새로운 C2 테스트에는 SKIP이 없다. 원격 CI는 최종 push 뒤 해당 제출 SHA로 조회해 마지막 응답에 기록한다. 로컬 PASS는 원격 CI PASS가 아니다.

초기 환경 문제와 처리:

- 샌드박스에서 asyncio executor 종료가 멈춰 진단 후 해당 실행을 중단했다. 테스트 자체 기준/timeout을 늘리지 않고 정상 IPC 환경에서 같은 테스트를 재실행했다. Node도 샌드박스에서는 파일 단위 70건만 표시되어 정상 IPC 환경에서 실제 660개 subtest를 확인했다. 중단한 실행을 PASS로 세지 않았다.
- 전용 품질도구 설치 시 기본 index 네트워크 접근 실패와 PyPI의 `No matching distribution found for ruff==0.6.9`가 발생했다. 기존 프로젝트에 이미 설치된 **같은 Ruff 0.6.9**를 사용해 검사했다. 설치 실패를 검사 실패/성공과 혼동하지 않는다.
- local browser E2E는 NOT_RUN: C2는 UI/공용 파일을 변경하지 않았고 이 clone에 Playwright 프로젝트 의존성/Chromium을 설치하지 않았다. 관련 JS 단위·syntax 검사는 실행했다. remote workflow가 실행되면 해당 SHA의 실제 결과를 별도 확인한다.
- ROS/native Nav2 simulation, 실제 모델·RGB replay, 실제 로봇/센서/자세/terrain/주행: 모두 NOT_RUN. 합성 테스트 통과는 물리 규정 충족·현장 안전성·실물 qualification을 증명하지 않는다.

전체 원시 실행 로그는 로컬 작업 폴더에만 보관한다. 원격에는 작은 검증 JSON과 요약만 올린다. 업로드하지 않은 로그/Actions artifact 링크를 만들지 않는다.

## D. 의존성과 통합 참고

다른 역할 브랜치를 읽거나 merge/cherry-pick하지 않았다. 다른 브랜치 참고 SHA는 없음이며 브랜치 간 호환성은 NOT_RUN이다. D0/C4가 제공할 관측은 이 adapter의 component age/sequence/epoch와 signal association에 맞춰야 한다. C3의 실제 Nav2 결과는 native goal/command 통합 검증의 추가 입력이며 C2 fake 테스트로 대체하지 않는다.

예상 충돌은 공용 연결 단계의 `mission_routes/service.py`, `wiring.py`, `application/mission_coordinator.py`, 기존 최종 command consumer다. C2 branch 자체는 이 파일을 수정하지 않는다. 권장 순서는 별도 검토→사용자 통합 승인→별도 통합 브랜치에서 C2 소스 채택→C1의 durable ledger/owner barrier/registry 연결→D0/C4 관측 계약 대조→단일 authority/watchdog 검증→별도 승인된 native/실물 qualification이다. 이번 제출은 이 중 첫 검토 대상만 제공한다.

rollback은 C2에서 추가한 파일만 제거한다. schema/storage migration·지도·온보드 설정 변경은 없다. `.github/workflows/ci.yml`을 확인했으며 push workflow는 GitHub-hosted `hardware-free-tests` 두 matrix뿐이고 robot 배포/service/SSH 단계는 없다. 제출은 이 브랜치만 명시적으로 push하며 main/다른 브랜치/PR/auto-merge는 변경하지 않는다.
