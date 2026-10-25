# C2 Round3 — 최초 수신 시각과 기존 C1 runtime 연결

작업 브랜치 `review/20261024-c2-mission-adapter`, 실제 시작/검토 기준 `ae52d9899c743221c88c9e0e1bab2a4a543103eb`. 시작 시 local/remote HEAD가 일치했고 작업 트리는 깨끗했다. 구현 검증 커밋은 `135da05adb9206f13505ef63cfd5710f4dde7fb4`이며 최종 문서 포함 SHA는 제출 응답에서 별도로 보고한다.

원격 main은 시작에 `104692fa0070ef085eee918913ea05fdb2d88c05`를 확인했다. C1 r2와 C4는 아래 exact SHA였으며 C1의 이전 `review/20261024-c1-ci-integration`과 실제 r2 브랜치를 구분했다. L1/lidar 이름의 원격 검토 브랜치는 이번 조회에 없었으므로 별도 L1 브랜치 통합 여부는 확인 불가다. 이를 오프라인 작업의 차단점으로 삼지 않았고 main의 LiDAR/위치추정/자동 초기값 파일을 수정하지 않았다.

## 이번에 닫은 실제 연결 차이

- 최신 C4의 `first_received_s`, `source_age_at_first_receipt_s`, `processed_s`, `identity_verified`를 코드에서 사용한다. `project_signal`은 실제 주입된 C4 `signal_fragment(..., received_s=first)`를 호출한 뒤 `join_signal`로 independent facts에 결합한다. C4 소스/보고서는 C2 브랜치에 복사하거나 통합하지 않았다.
- 별도 인자는 context 값을 확인하는 용도다. caller/polling이 처음 수신 시각/age/처리 완료시각을 바꾸면 거부한다. legacy 완료시각 age가 함께 있으면 명시적 최초 age와 모순 여부를 검사하고, 누락된 최초 age를 기본 역산으로 보충하지 않는다.
- C2 coordinator port에 기존 C1 r2 `native_owner` API 호환을 구현했다. r2의 `native_barrier`, owner token, success/cancel continuation, external pause 및 STOP fence를 재설계하지 않는다. C2의 별도 callback 경로도 보존한다.
- `NativeRuntime.continuation_proven`, `require_dispatch_authorized`, `command_context`, `scope`를 제공한다. C1 session이 `_stop_requested`, `_constraint`, `_goal`, normalizer 사본을 읽어 판단하지 않아도 된다. snapshot에는 bounded request 수가 포함된다.
- C1 r2의 각 source timestamp 경과 검증과 C2의 HOLD ACK 이후 source-supported 구간 검증을 함께 유지했다. 비교는 같은 producer clock 안의 delta만 사용한다. fixture의 source_stamp_ns도 가상 초 단위 시계에 맞게 수정했다.
- 새 generation HOLD 미설치/ACK 지연 때 EXIT_PREPARE에서 기다린다. 설치된 consumer ACK와 유효한 원래 dwell frame이 모두 있어야 goal을 생성한다. 준비 중 RED를 무시하지 않는다. 계획 대기 후 guard 재검사로 STOP/pause/old RELEASE/만료 proof를 차단한다.

수정 파일: C2 `adapter.py`, `contracts.py`, `coordinator.py`, `fragments.py`, `observations.py`, `runtime.py`, `state.py`; 전용 `helpers.py`, `test_runtime_contract.py`; 신규 `dependency_overlay.py`, `test_round3_cross_contract.py`; C2 `HANDOFF.md`, `WIRING_PROPOSAL.md`, 이 `ROUND3.md`. 삭제/이동/바이너리/공용 파일 수정 없음. 새 terrain/parking FSM, 외부 모니터, timer, publisher, 새 설치 환경은 만들지 않았다.

## 실제 고정 dependency 및 교차 실행

| 의존성 | 정확한 읽기 전용 SHA | 실제 사용 |
|---|---|---|
| C4 `review/20261024-c4-traffic-replay` | `380800ca9e211495769fe60ee8221e3f4fb40f16` | 실제 projection/config/frames/pipeline. detector·JPEG·clock은 합성 |
| C1 `review/20261024-c1-integration-r2` | `765622ecbe20dd29b40296dd2ad24fa508ac9443` | 실제 MissionCoordinator, SessionGate. navigation/계획 대기·물리 사실은 합성 |

`tests/competition_native/dependency_overlay.py`는 Git 객체를 `git show exact_sha:path`로 읽어 temporary directory에 로드한다. 다른 브랜치 checkout/index를 바꾸거나 그 코드를 tracked 파일로 추가하지 않는다. 테스트가 끝나면 overlay를 정리한다. 테스트 중 fetch/install/network는 없다. 파일을 구할 수 없으면 NOT_RUN/SKIP을 명시한다. 이번 검증에서는 `C2_CROSS_REQUIRED=1`로 의존성 누락이 실패가 되도록 실행했고 교차 테스트가 실제 수행됐다. CI의 shallow checkout에서 해당 객체가 없으면 교차 부분은 NOT_RUN이며 C1 통합 job에서 exact 객체를 확보해야 한다.

C4 실제 projection 수치 회귀: first=10.00, age_at_first=.02, processed=10.08, now=10.15 → age=.17. now=10.23의 .25 경계는 C4와 C2 모두 허용, 10.230001은 만료다. C2 freshness는 동등한 deadline 비교를 사용해 .25 경계의 소수 표현 오차를 피하며 epsilon으로 TTL을 늘리지 않는다. 같은 원래 샘플을 10.20에 polling해도 receipt=10.00이 유지된다. 처리 완료/polling 시각을 first로 전달, 최초 age 감소, 서로 모순인 legacy/new age, unverified identity/clock/association, config/epoch 오류, 같은 stamp에 새 seq, 재시작의 old packet을 거부한다.

동일한 작은 합성 JPEG 바이트를 실제 C4 `from_owner_jpeg → TrafficPipeline → signal_fragment → project_signal/join_signal → Normalizer`로 반복 입력했다. 실제 seq/stamp가 전진할 때만 신선도가 전진했고 같은 내용이라는 이유로 새 source frame을 막지 않았다. 원본 사용자 영상·가중치를 사용하거나 업로드하지 않았다.

C4 pipeline이 참조하는 D0 color/temporal helper는 기존 C2 checkout에 보존된 버전이다. 최신 D0 브랜치를 채택하거나 전체 D0 결합을 검증했다는 의미는 아니다.

C1 교차 테스트는 **원본 session 전체를 수정해 실행한 검사로 주장하지 않는다**. 원본 r2 coordinator/SessionGate를 사용하며 아래 public API call site를 전용 테스트 harness에서 연결했다. 기존 C1 session/ingress/worker/service/API/CI 파일은 그대로다. 공용 파일 적용은 C1의 작업이다.

## C1 적용 지점과 최소 변경

### session.py: public NativeRuntime 사용

`SoftwareNativeSession.create`는 기존 `SessionGate`, `CoordinatorNavigationPort(..., native_owner=self.token)`와 `bind_native_owner`를 유지한다. 기존 compiled/pins/admission 검증도 유지한다. C2의 구성은 다음과 같다.

```python
self.runtime = configure_action(
    RuntimeConfig(action, scope, policy, bindings, event_binding,
                  receiver_clock_id, activation),
    RuntimePorts(self.port, self.gate), clock=clock,
)
```

`event_binding=EventBinding(trusted_owner_broker_id, broker_epoch)`와 같은 호스트의 receiver clock identity를 명시한다. source/receiver TTL <=.25, 연속 stop gap=.5는 별도다. 명시적 synthetic activation을 사용하고 public motion capability 등록은 하지 않는다.

다음은 C1 소유 함수들의 최소 대체 내용이며 C2 브랜치에서 공용 파일을 수정하는 patch가 아니다.

```diff
 def _continuation_proven(self, *, completed=False, starting=False):
-    # adapter._stop_requested / state / _valid_ack / _constraint / preview proof
+    return not self.closed and self.runtime.continuation_proven(
+        completed=completed, starting=starting)

 # start operation, existing durable admission retained
-    return await self.adapter.start(request_id, approach_pose=approach_pose)
+    return await self.runtime.start(request_id, approach_pose=approach_pose)

 # observe/tick application: remove normalizer deepcopy/preview and self.proof
-    result = await self.adapter.observe(packet)
+    result = await self.runtime.receive(packet) if packet is not None else await self.runtime.tick()
+    phase = result["state"]["phase"]
+    scope = self.runtime.scope
 # finish_native still uses C1 admission/token and actual goal ownership
-    actual_goal_id=self.adapter._goal.actual_goal_id
+    actual_goal_id=result["actual_goal_id"]

 # command(): preserve the existing port.goal_observation/current mission owner check
-    # inspect adapter normalizer/state/private constraint
+    ctx = self.runtime.command_context()
+    # boundary.evaluate(..., goal_scope=ctx.scope if owned else None,
+    #   goal_receipt_s=ctx.goal_receipt_s, inputs_fresh=ctx.inputs_fresh and owned,
+    #   estop=ctx.estop, collision=ctx.collision)

 # stop(): these C1 immediate fences MUST remain before awaiting durable IO
     self.closed = True
     self.gate.retire()
-    coordinator.fence_native_stop(self.adapter.scope.mission_run_id, token=self.token)
+    coordinator.fence_native_stop(self.runtime.scope.mission_run_id, token=self.token)
 # inside existing stop operation/finally worker.close()
-    return await self.adapter.stop(request_id, restart=restart)
+    return await (self.runtime.cleanup(request_id) if restart else self.runtime.stop(request_id))
```

상태 분기는 `runtime.snapshot()["state"]`, 현재 constraint는 snapshot.pending.constraint, 실제 goal ID는 snapshot.actual_goal_id를 쓴다. 초기 approach tracking의 별도 gate RELEASE 정책 및 nav/mission ownership 검사는 기존 C1이 계속 책임진다. `command_context`는 입력 판정이지 owner/lease나 실제 명령이 아니다. adapter 내부 속성에 대한 새 의존성을 만들지 않는다.

### coordinator preflight: await 뒤 guard 재검사

기존 `MissionCoordinator._dispatch_current_locked`는 planning을 await한다. 앞서 통과한 guard가 이 대기 뒤에도 유효하다는 보장이 없으므로, 기존 STOP 확인 및 dispatch 직전에 등록된 native owner guard를 다시 검사한다. 검사식은 `owner.guard(starting=mission.current_index == 0)`이다. 또는 기존 C1 preflight callback 마지막에서 `runtime.require_dispatch_authorized(starting=...)`를 호출한다. **이번 교차 테스트는 후자의 실제 callable을 r2 coordinator에서 실행했다.** 동일 비재진입 lock을 C2가 다시 잡지 않는다.

EXIT_PENDING 문자열만 EXIT_PREPARE로 바꾸는 수정이 아니다. C2가 소유한 immutable dwell proof, 현재 consumer의 exact HOLD ACK, 현재 clock의 expiry, stop_requested를 public guard가 함께 확인한다. C1의 owner token/external_stop/STOP/pins/visit 검사는 추가로 유지한다. C1 r2의 새 generation HOLD·실제 취소와 native 완료의 구분을 제거하지 않는다.

### ingress.py: C4 first receipt 연결

[최신 WIRING_PROPOSAL 예제](../../../mission-competition/native-adapter/WIRING_PROPOSAL.md)의 `project_signal`을 호출한다. 기존 `signal_fragment(..., received_s=sample.processed_s)`와 `ComponentStamp(..., received_s=...)` 직접 구성은 제거한다. `SignalBinding`에는 신호 producer/epoch/source clock, C4 config hash, binding ID, model SHA, signal/crossing ID, verified receiver clock ID를 고정한다. runtime은 scope와 receiver session nonce를 제공한다. 색은 feet/STOP/path를 채우지 않는다.

`processed_s`의 기준은 **observation.context.processed_s**다. worker가 별도 후처리 시각을 기록한다면 그것을 context의 처리 완료 시각 대신 넣지 않는다. 별도 인자가 있다면 frame의 원래 received_s/source_age_s와 context의 값이 같아야 한다. 세 시각은 같은 ingress host/clock이어야 하며 remote monotonic 전달은 별도 검증 필요다. fixture-clock replay는 C1의 명시적 synthetic 전용 분기로 유지한다.

### request ledger

C2의 start/stop request ledger, effect ledger, event ledger는 bounded 상태다. 1,200번의 반복 tick 전후 `snapshot.request_counts`가 같고 gate의 HOLD request도 한 개였다. tick이 source time/dwell을 늘리지 않았다. C1의 256 durable ledger/rate 정책은 수정하지 않았으며 C1이 자신의 effect journal/관측 queue 정책을 적용한다. 이 결과를 C1 service.store.save 횟수 검증으로 확대하지 않는다.

## 실제 검증

```bash
# Exact objects must be available beforehand; tests never fetch by themselves.
# The 24 cross-contract tests are included in both discovery commands below.
C2_CROSS_REQUIRED=1 python -m unittest discover -s tests/competition_native -t . -v
C2_CROSS_REQUIRED=1 python -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
ruff check --no-cache robot_dashboard scripts tests/competition_native
python -m mypy --config-file mypy.ini
python scripts/check_repository_secrets.py
```

| 실제 실행 검사 | 결과 |
|---|---|
| C2 전용 unittest discovery | **107/107 PASS**, 1.256초. 기존 83개 + 신규 C1 19개/C4 5개 교차 검사 |
| 전체 Python unittest discovery | **2,798개 실행: 2,796 PASS, 2 SKIP**, 104.856초 |
| JavaScript `node --test tests/*.mjs` | **660/660 PASS**, 2.125초 |
| frontend syntax | **104 modules PASS** |
| Ruff (`robot_dashboard scripts tests/competition_native`) | **PASS** |
| mypy (`mypy.ini`) | **설정된 4개 파일 PASS**. 전체 native package typing 검증으로 확대하지 않음 |
| staged diff whitespace / repository secret scan | **PASS** |

전체 Python의 SKIP 2개는 optional rosbags backend 미설치와 `PCD_EDIT_NODE` 미지정이다. 기존 fixture의 `BLOCKED`/`COMPUTED_DECLARED_INPUTS` 출력은 해당 테스트의 예상 출력이며 실패가 아니다. 위 검사는 기능 커밋 `135da05adb9206f13505ef63cfd5710f4dde7fb4`의 코드에 대해 수행했다. 후속 커밋은 이 결과 문서만 추가한다.

환경은 기존 Python 3.12.3/Pydantic 2.13.4 venv, NumPy/OpenCV/Pillow 기존 설치, Node 24.19.0, Ruff 0.6.9와 기존 quality venv의 mypy다. 새 dependency 설치 없음. 샌드박스 asyncio/IPC 종료 제한이 알려져 있어 로봇/외부 서비스 없는 테스트를 승인된 escalation 환경에서 실행했다. 전체 suite는 제출 후보에 대해 실행했으며 설치/초기 하네스를 반복하지 않았다.

개발 중 새 교차 테스트가 정확한 .03→2.03 stop 구간에서 소수 뺄셈 오차로 exit를 한 tick 늦추는 문제를 재현했다. deadline 비교로 수정하고 기존 2초 미만 거부 테스트도 유지했다. 신규 partial packet 테스트의 잘못된 UNKNOWN goal enum은 navigation component를 제외하는 실제 partial-observation fixture로 수정했다. 기존 assertion을 삭제하거나 물리 정지/TTL 임계값을 완화하지 않았다.

PASS 범위는 synthetic 알고리즘·실제 Python dependency 호출·기존 coordinator/consumer의 소프트웨어 계약이다. native Nav2/ROS, 실제 모델 추론 정확도, 실제 발/STOP/출발 producer, 물리 actuator watchdog/ACK는 NOT_RUN 또는 INPUT_REQUIRED이며 live_ready=false를 유지한다. 로컬 공용 browser E2E는 C1 소유이며 재수정/재구축하지 않았다. 원격 CI는 최종 exact SHA에 대해 조회하여 제출 응답에 기록한다. 원격 artifact를 받지 않았으며 로컬 raw logs는 브랜치에 업로드하지 않았다.

## 다음 한 가지

**C1이 이 exact C2 delta와 위 session/ingress/preflight 호출 변경을 자신의 기존 r2 통합 브랜치에 증분 적용하고, 자신의 실제 session·worker·브라우저 경로를 재검증하는 것**이 남은 한 가지 작업이다. 필요한 입력은 위에 고정한 C4/C1 SHA 및 기존 C1 token/clock/producer binding이며, 물리 producer 부족은 이 synthetic 통합을 막지 않는다.

이 채팅은 main 병합/PR/로봇 접속/서비스 변경/배포/실이동을 수행하지 않았다. 사용자 및 다른 역할의 작업을 reset하거나 덮어쓰지 않았다. rollback 범위는 이 C2 패키지/전용 테스트/문서 delta다.
